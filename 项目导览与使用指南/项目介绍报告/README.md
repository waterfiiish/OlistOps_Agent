# OlistOps Agent 项目介绍报告

本目录是面向项目展示、技术面试和从零阅读的正式报告包。

## 主要文件

- `OlistOps_Agent_项目介绍与技术报告.docx`：可编辑 Word 版。
- `OlistOps_Agent_项目介绍与技术报告.pdf`：固定版式 PDF 版。
- `OlistOps_Agent_项目介绍与技术报告.html`：PDF 的同源 HTML。
- `actual_evidence.json`：报告生成前从本地 API 与 PostgreSQL 采集的真实证据。
- `assets/`：本地前端、数据质量、Swagger、RAG、Agent Run 和数据库截图。

## 字体

正文中文为宋体五号（10.5 pt），英文与数字为 Times New Roman 10.5 pt。
DOCX 在 OpenXML 的东亚字体和拉丁字体中分别声明；HTML/PDF 使用相同字体回退顺序。

## 重新生成

服务已启动时，在项目根目录执行：

```powershell
python scripts/capture_report_evidence.py
python scripts/capture_report_screenshots.py
python scripts/generate_project_report.py
```

报告会覆盖本目录中同名的 DOCX、HTML 和 PDF。截图和实时数字应在代码、数据或配置变化后重新采集。
