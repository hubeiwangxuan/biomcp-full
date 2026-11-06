# BioMCP Full Server

生物医学情报一体化 MCP Server，覆盖 9 大权威数据源 + HTML 网页发布能力。

## 工具列表

| 工具名 | 功能 | 数据源 |
|--------|------|--------|
| search_literature | 生物医学文献检索 | Europe PMC / PubMed |
| query_gene | 基因信息查询 | MyGene.info |
| query_drug | 药物信息查询 | MyChem.info / DrugBank |
| search_clinical_trials | 临床试验检索 | ClinicalTrials.gov |
| query_clinvar | 变异致病性查询 | ClinVar (NCBI) |
| search_adverse_events | 药物不良事件检索 | OpenFDA FAERS |
| query_uniprot | 蛋白信息查询 | UniProt |
| search_reactome | 信号通路查询 | Reactome |
| search_citations | 文献引用网络查询 | Semantic Scholar |
| publish_html_page | HTML 网页发布 | ShipStatic |
| publish_file | Word/Excel/PDF 文件发布 | ShipStatic |

## 部署到 Railway

### 方式 1：GitHub + Railway 自动部署（推荐）

1. 新建 GitHub 仓库，把本项目代码 push 上去
2. 登录 [Railway](https://railway.app)，点击 "New Project" → "Deploy from GitHub repo"
3. 选择你的仓库，Railway 会自动识别 Dockerfile 并部署
4. 部署完成后，在 Settings → Networking 中生成公网域名
5. MCP 端点地址：`https://你的域名.up.railway.app/mcp`

### 方式 2：Render 部署

1. Fork 本仓库到你的 GitHub
2. 登录 [Render](https://render.com)，新建 Web Service
3. 选择你的仓库，Runtime 选 Docker
4. 部署完成后获得公网 URL

## Coze 接入

1. Coze 智能体 → 添加 MCP 服务 → HTTP (Streamable HTTP)
2. 填入 MCP 端点地址：`https://你的域名/mcp`
3. 无需鉴权（如需加 Token，可在 server.py 中扩展）

## 本地测试

```bash
pip install -r requirements.txt
python server.py
```

访问 `http://localhost:8000/mcp` 即可测试。

## 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| PORT | 8000 | 服务端口 |
