import pytest

from packages.agent_runtime.workflow import OlistOpsWorkflow


def test_normalize_chinese_month_and_sample_threshold() -> None:
    workflow = OlistOpsWorkflow()
    state = workflow.normalize_request(
        {
            "user_query": "分析 2018 年 7 月配送表现，订单量不少于 20 的卖家",
        }
    )
    assert state["time_range"] == {
        "start_date": "2018-07-01",
        "end_date": "2018-07-31",
    }
    assert state["entity_filters"]["min_orders"] == 20


def test_demo_query_routes_to_delivery_even_when_reviews_are_mentioned() -> None:
    state = {
        "user_query": "比较延期订单与按时订单的平均评分，并分析差评",
        "entity_filters": {"seller_id": None},
    }
    assert OlistOpsWorkflow.route_intent(state)["intent"] == "delivery_analysis"


def test_seller_id_has_priority() -> None:
    seller_id = "06a2c3af7b3aee5d69171b0e14f0ee87"
    state = {
        "user_query": f"诊断 seller {seller_id}",
        "entity_filters": {"seller_id": seller_id},
    }
    assert OlistOpsWorkflow.route_intent(state)["intent"] == "seller_diagnostic"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("给我 2018 年经营总览和取消率", "operations_overview"),
        ("分析 2017 年到 2018 年的月度趋势", "trend_analysis"),
        ("比较各州地区的履约表现", "geography_analysis"),
        ("哪些类别的运费占比最高", "freight_analysis"),
        ("分析信用卡和 boleto 支付方式", "payment_analysis"),
    ],
)
def test_extended_intent_routes(query: str, expected: str) -> None:
    state = {"user_query": query, "entity_filters": {"seller_id": None}}
    assert OlistOpsWorkflow.route_intent(state)["intent"] == expected


def test_critic_accepts_structured_answer_with_complete_citations() -> None:
    workflow = OlistOpsWorkflow()
    result = workflow.critic(
        {
            "draft_answer": (
                "# 分析报告\n\n## 数据事实\n\n有证据 [K-001]。\n\n"
                "## 建议\n\n执行复核。"
            ),
            "retrieved_chunks": [{"chunk_id": "one"}],
            "warnings": [],
        }
    )
    assert result["critic_report"]["passed"] is True
    assert result["critic_report"]["score"] == 1.0
    assert result["critic_report"]["corrected"] is False
