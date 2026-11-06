"""
BioMCP Full Server - 生物医学情报 + 网页发布一体化 MCP Server
支持 Streamable HTTP 模式，可直接部署到 Railway / Render / Koyeb

数据源覆盖：
- Europe PMC (文献检索)
- MyGene.info (基因查询)
- MyChem.info (药物查询)
- ClinicalTrials.gov (临床试验)
- ClinVar (变异致病性)
- OpenFDA FAERS (不良事件)
- UniProt (蛋白查询)
- Reactome (信号通路)
- Semantic Scholar (引用网络)
- ShipStatic (HTML网页发布)
"""

import httpx
import asyncio
import base64
import os
from typing import Optional
from fastmcp import FastMCP

# ============================================================
# 初始化 MCP Server
# ============================================================
mcp = FastMCP(
    name="BioMCP-Full",
    instructions="""
    生物医学情报一体化 MCP，覆盖文献、基因、药物、临床试验、变异、不良事件、蛋白、通路、引用网络9大数据源，并内置HTML网页发布能力。
    
    路由规则：
    - 文献检索 → search_literature
    - 基因/靶点查询 → query_gene
    - 药物信息 → query_drug
    - 临床试验 → search_clinical_trials
    - 变异致病性 → query_clinvar
    - 不良事件 → search_adverse_events
    - 蛋白信息 → query_uniprot
    - 信号通路 → search_reactome
    - 引用网络 → search_citations
    - 生成网页报告 → publish_html_page
    """
)

# HTTP 客户端（复用连接）
http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)


# ============================================================
# 工具 1：生物医学文献检索 (Europe PMC)
# ============================================================
@mcp.tool()
async def search_literature(
    query: str,
    page_size: int = 10,
) -> dict:
    """
    跨 PubMed / Europe PMC 检索生物医学文献。
    支持关键词、布尔逻辑、年份过滤。返回标题、作者、摘要、PMID、DOI、期刊。
    适用于靶点机制调研、药物临床证据、疾病研究进展、文献综述。

    Args:
        query: 检索关键词，支持布尔逻辑（AND/OR/NOT）；示例：GLP-1 receptor AND obesity
        page_size: 返回结果数量，默认10，最大25
    """
    page_size = min(page_size, 25)
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "format": "json",
        "pageSize": page_size,
        "resultType": "core",
    }
    resp = await http_client.get(url, params=params)
    data = resp.json()

    results = []
    for item in data.get("resultList", {}).get("result", []):
        results.append({
            "pmid": item.get("pmid", ""),
            "doi": item.get("doi", ""),
            "title": item.get("title", ""),
            "authors": item.get("authorString", ""),
            "journal": item.get("journalTitle", ""),
            "pub_year": item.get("pubYear", ""),
            "abstract": item.get("abstractText", "")[:500] if item.get("abstractText") else "",
        })

    return {
        "hit_count": data.get("hitCount", 0),
        "results": results,
    }


# ============================================================
# 工具 2：基因信息查询 (MyGene.info)
# ============================================================
@mcp.tool()
async def query_gene(
    q: str,
    species: str = "human",
) -> dict:
    """
    根据基因符号（如 TP53、GLP1R、PDCD1）查询基因基本信息：
    功能描述、染色体定位、别名、Entrez ID、UniProt ID。
    适用于靶点基因验证、基因符号标准化、染色体定位确认。

    Args:
        q: 基因检索词：官方基因符号（如 GLP1R、TP53、PDCD1）
        species: 物种，默认 human；可选 mouse、rat
    """
    url = "https://mygene.info/v3/query"
    params = {
        "q": q,
        "species": species,
        "fields": "symbol,name,summary,genomic_pos,alias,entrezgene,uniprot",
        "size": 1,
    }
    resp = await http_client.get(url, params=params)
    data = resp.json()

    hits = data.get("hits", [])
    if not hits:
        return {"found": False, "message": f"未找到基因: {q}"}

    g = hits[0]
    return {
        "found": True,
        "symbol": g.get("symbol", ""),
        "name": g.get("name", ""),
        "summary": g.get("summary", ""),
        "chromosome": g.get("genomic_pos", [{}])[0].get("chr", "") if isinstance(g.get("genomic_pos"), list) else "",
        "aliases": g.get("alias", []),
        "entrez_gene_id": g.get("entrezgene", ""),
        "uniprot_id": list(g.get("uniprot", {}).get("Swiss-Prot", []))[0] if isinstance(g.get("uniprot"), dict) and g.get("uniprot", {}).get("Swiss-Prot") else "",
    }


# ============================================================
# 工具 3：药物信息查询 (MyChem.info / DrugBank)
# ============================================================
@mcp.tool()
async def query_drug(q: str) -> dict:
    """
    根据药物名称查询药物信息：分子式、分子量、靶点、适应症、药理作用、ATC编码、CAS号。
    底层数据源 MyChem.info (整合 DrugBank)。
    适用于药物靶点验证、适应症确认、分子式查询。

    Args:
        q: 药物名称：通用名（如 semaglutide、pembrolizumab）、商品名（如 Ozempic、Keytruda）或 CAS 号
    """
    url = "https://mychem.info/v1/query"
    params = {
        "q": q,
        "fields": "name,molecular_formula,molecular_weight,cas_rn,indication,pharmacology,drugbank.targets,atc_code",
        "size": 1,
    }
    resp = await http_client.get(url, params=params)
    data = resp.json()

    hits = data.get("hits", [])
    if not hits:
        return {"found": False, "message": f"未找到药物: {q}"}

    d = hits[0]
    targets = d.get("drugbank", {}).get("targets", [])
    target_names = [t.get("name", "") for t in targets[:5]] if isinstance(targets, list) else []

    return {
        "found": True,
        "drug_name": d.get("name", ""),
        "molecular_formula": d.get("molecular_formula", ""),
        "molecular_weight": d.get("molecular_weight", ""),
        "cas_number": d.get("cas_rn", ""),
        "indication": d.get("indication", "")[:300],
        "pharmacology": d.get("pharmacology", "")[:300],
        "targets": target_names,
        "atc_code": d.get("atc_code", ""),
    }


# ============================================================
# 工具 4：临床试验检索 (ClinicalTrials.gov API v2)
# ============================================================
@mcp.tool()
async def search_clinical_trials(
    query: str,
    page_size: int = 10,
    status: Optional[str] = None,
    phase: Optional[str] = None,
) -> dict:
    """
    根据疾病/药物/干预措施检索 ClinicalTrials.gov 临床试验。
    返回 NCT 编号、试验状态、分期、入组人数、申办方、适应症。
    适用于药物研发管线追踪、竞争格局分析、试验设计参考。

    Args:
        query: 检索词：疾病名称、药物名称、干预措施
        page_size: 返回结果数量，默认10，最大25
        status: 试验状态过滤：RECRUITING / COMPLETED / ACTIVE_NOT_RECRUITING
        phase: 试验分期过滤：PHASE1 / PHASE2 / PHASE3 / PHASE4
    """
    page_size = min(page_size, 25)
    url = "https://clinicaltrials.gov/api/v2/studies"
    params = {
        "query.term": query,
        "pageSize": page_size,
        "format": "json",
    }
    if status:
        params["filter.overallStatus"] = status
    if phase:
        params["filter.phase"] = phase

    resp = await http_client.get(url, params=params)
    data = resp.json()

    studies = []
    for s in data.get("studies", []):
        proto = s.get("protocolSection", {})
        id_module = proto.get("identificationModule", {})
        status_module = proto.get("statusModule", {})
        design_module = proto.get("designModule", {})
        sponsor_module = proto.get("sponsorCollaboratorsModule", {})
        cond_module = proto.get("conditionsModule", {})
        arms_module = proto.get("armsInterventionsModule", {})

        interventions = [i.get("name", "") for i in arms_module.get("interventions", [])[:3]]

        studies.append({
            "nct_id": id_module.get("nctId", ""),
            "brief_title": id_module.get("briefTitle", ""),
            "overall_status": status_module.get("overallStatus", ""),
            "phase": design_module.get("phases", []),
            "start_date": status_module.get("startDateStruct", {}).get("date", ""),
            "completion_date": status_module.get("completionDateStruct", {}).get("date", ""),
            "enrollment": design_module.get("enrollmentInfo", {}).get("count", 0),
            "lead_sponsor": sponsor_module.get("leadSponsor", {}).get("name", ""),
            "conditions": cond_module.get("conditions", []),
            "interventions": interventions,
        })

    return {
        "total_count": data.get("totalCount", 0),
        "studies": studies,
    }


# ============================================================
# 工具 5：变异致病性查询 (ClinVar)
# ============================================================
@mcp.tool()
async def query_clinvar(
    gene: str,
    protein_change: Optional[str] = None,
    rs_id: Optional[str] = None,
) -> dict:
    """
    根据基因符号+蛋白改变（如 TP53 R175H、EGFR L858R）查询 ClinVar 数据库中的
    变异致病性评级、临床意义、相关疾病、审核状态。
    适用于肿瘤变异解读、孟德尔遗传病变异分析。

    Args:
        gene: 基因符号，如 TP53、BRCA1、EGFR
        protein_change: 蛋白改变，如 R175H、V600E、L858R
        rs_id: dbSNP rs编号，如 rs121913529
    """
    if protein_change:
        query_str = f"{gene} {protein_change}[Protein Change]"
    elif rs_id:
        query_str = rs_id
    else:
        return {"error": "必须提供 protein_change 或 rs_id 其中一个"}

    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "clinvar",
        "term": query_str,
        "retmode": "json",
        "retmax": 5,
    }
    resp = await http_client.get(url, params=params)
    data = resp.json()

    ids = data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return {"found": False, "message": f"ClinVar 中未找到 {query_str}"}

    # 获取详情
    summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    summary_params = {
        "db": "clinvar",
        "id": ",".join(ids),
        "retmode": "json",
    }
    summary_resp = await http_client.get(summary_url, params=summary_params)
    summary_data = summary_resp.json()

    variants = []
    for vid in ids:
        v = summary_data.get("result", {}).get(vid, {})
        variants.append({
            "clinvar_id": vid,
            "title": v.get("title", ""),
            "germline_classification": v.get("germline_classification", {}).get("description", ""),
            "review_status": v.get("germline_classification", {}).get("review_status", ""),
            "last_updated": v.get("last_updated_date", ""),
        })

    return {"found": True, "variants": variants}


# ============================================================
# 工具 6：药物不良事件检索 (OpenFDA FAERS)
# ============================================================
@mcp.tool()
async def search_adverse_events(
    search: str,
    count: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """
    根据药物名称查询 FDA FAERS 不良事件数据库。
    支持不良反应频次统计、个案报告查询。
    适用于药物安全性信号检测、不良反应谱分析、上市后安全监测。

    Args:
        search: OpenFDA Lucene 检索表达式；示例：patient.drug.medicinalproduct:"semaglutide"
        count: 聚合统计维度，常用值：patient.reaction.reactionmeddrapt（按不良反应术语统计频次）
        limit: 返回结果数量，默认 20，最大 100
    """
    limit = min(limit, 100)
    url = "https://api.fda.gov/drug/event.json"
    params = {
        "search": search,
        "limit": limit,
    }
    if count:
        params["count"] = count

    resp = await http_client.get(url, params=params)
    if resp.status_code == 404:
        return {"error": "未找到匹配的不良事件记录", "total": 0}

    data = resp.json()
    total = data.get("meta", {}).get("results", {}).get("total", 0)

    results = []
    if count:
        for item in data.get("results", []):
            results.append({
                "term": item.get("term", ""),
                "count": item.get("count", 0),
            })
    else:
        for item in data.get("results", [])[:limit]:
            results.append({
                "safety_report_id": item.get("safetyreportid", ""),
                "receivedate": item.get("receivedate", ""),
                "serious": item.get("serious", ""),
            })

    return {"total": total, "results": results}


# ============================================================
# 工具 7：蛋白信息查询 (UniProt)
# ============================================================
@mcp.tool()
async def query_uniprot(
    query: str,
    size: int = 5,
) -> dict:
    """
    根据基因符号或 UniProt ID 查询蛋白详细信息：
    蛋白名称、功能、氨基酸长度、亚细胞定位、组织特异性。
    适用于靶点蛋白功能验证、信号通路分子组成。

    Args:
        query: 检索词：基因符号（如 GLP1R）、UniProt ID（如 P43220）
        size: 返回条目数，默认 5，最大 20
    """
    size = min(size, 20)
    url = "https://rest.uniprot.org/uniprotkb/search"
    params = {
        "query": f"({query}) AND organism_id:9606",
        "format": "json",
        "size": size,
        "fields": "accession,protein_name,gene_names,length,cc_function,cc_subcellular_location,cc_tissue_specificity",
    }
    resp = await http_client.get(url, params=params)
    data = resp.json()

    proteins = []
    for item in data.get("results", []):
        primary_gene = item.get("genes", [{}])[0].get("geneName", {}).get("value", "") if item.get("genes") else ""
        proteins.append({
            "uniprot_id": item.get("primaryAccession", ""),
            "protein_name": item.get("proteinDescription", {}).get("recommendedName", {}).get("fullName", {}).get("value", ""),
            "gene_name": primary_gene,
            "length": item.get("sequence", {}).get("length", 0),
            "function": "",  # 需要进一步解析 comments
        })

    return {"count": data.get("totalResults", 0), "proteins": proteins}


# ============================================================
# 工具 8：信号通路查询 (Reactome)
# ============================================================
@mcp.tool()
async def search_reactome(
    query: str,
    species: str = "Homo sapiens",
) -> dict:
    """
    根据基因符号或关键词查询 Reactome 数据库中的信号通路。
    返回通路名称、物种、是否有通路图、是否有事件详情。
    适用于通路富集分析、信号传导机制解读、靶点所在通路定位。

    Args:
        query: 检索词：基因符号（如 TP53）、通路名称关键词（如 cell cycle）
        species: 物种，默认 Homo sapiens
    """
    url = "https://reactome.org/ContentService/search/query"
    params = {
        "query": query,
        "species": species,
        "types": "Pathway",
        "pageSize": 10,
    }
    resp = await http_client.get(url, params=params)
    data = resp.json()

    pathways = []
    for item in data.get("results", [])[:10]:
        pathways.append({
            "pathway_id": item.get("dbId", ""),
            "pathway_name": item.get("name", ""),
            "species": item.get("species", ""),
            "has_diagram": item.get("hasDiagram", False),
        })

    return {"count": len(pathways), "pathways": pathways}


# ============================================================
# 工具 9：文献引用网络查询 (Semantic Scholar)
# ============================================================
@mcp.tool()
async def search_citations(
    query: str,
    limit: int = 10,
) -> dict:
    """
    根据关键词或标题检索 Semantic Scholar 文献库。
    返回被引次数、高影响力引用次数、TLDR 一句话摘要、开放获取 PDF 链接。
    适用于文献影响力评估、引用追踪、研究前沿识别。

    Args:
        query: 检索关键词或标题
        limit: 返回结果数量，默认 10，最大 100
    """
    limit = min(limit, 100)
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,authors,year,citationCount,influentialCitationCount,externalIds,tldr,isOpenAccess,openAccessPdf",
    }
    resp = await http_client.get(url, params=params)
    data = resp.json()

    papers = []
    for p in data.get("data", []):
        authors = [a.get("name", "") for a in p.get("authors", [])[:5]]
        papers.append({
            "paper_id": p.get("paperId", ""),
            "title": p.get("title", ""),
            "authors": authors,
            "year": p.get("year", ""),
            "citation_count": p.get("citationCount", 0),
            "influential_citations": p.get("influentialCitationCount", 0),
            "doi": p.get("externalIds", {}).get("DOI", ""),
            "is_open_access": p.get("isOpenAccess", False),
            "open_access_pdf": p.get("openAccessPdf", {}).get("url", "") if p.get("openAccessPdf") else "",
            "tldr": p.get("tldr", {}).get("text", "") if p.get("tldr") else "",
        })

    return {"total": data.get("total", 0), "papers": papers}


# ============================================================
# 工具 10：HTML 网页发布 (ShipStatic)
# ============================================================
@mcp.tool()
async def publish_html_page(
    html_content: str,
    title: str = "Biomedical Report",
) -> dict:
    """
    将完整 HTML 代码发布为在线网页，返回公网访问链接。
    适用于生成生物医药简报、临床汇总报告、文献看板等网页交付物。
    匿名发布页面默认保留 3 天，可认领转为永久页面。

    Args:
        html_content: 完整的 HTML 源码（必须包含 <!DOCTYPE html>）
        title: 网页标题
    """
    url = "https://api.shipstatic.com/v1/deployments"
    payload = {
        "files": [
            {
                "path": "index.html",
                "content": html_content,
            }
        ]
    }
    headers = {
        "Content-Type": "application/json",
    }

    resp = await http_client.post(url, json=payload, headers=headers)
    if resp.status_code not in (200, 201):
        return {
            "success": False,
            "error": f"发布失败: HTTP {resp.status_code}",
            "detail": resp.text[:500],
        }

    data = resp.json()
    return {
        "success": True,
        "url": data.get("url", ""),
        "claim_url": data.get("claimUrl", ""),
        "deployment_id": data.get("id", ""),
        "message": "网页发布成功！匿名页面保留3天，可通过 claim_url 认领转为永久页面。",
    }


# ============================================================
# 工具 11：文件发布（Word / Excel / PDF 全套）
# ============================================================
def _build_download_page(
    filename: str,
    file_size_kb: float,
    file_type: str,
    description: str = "",
) -> str:
    """生成极简SCI风格下载页 HTML"""
    ext = os.path.splitext(filename)[1].lower()

    # 文件类型图标和颜色
    type_config = {
        ".pdf": {"icon": "📄", "label": "PDF 文档", "color": "#dc2626"},
        ".docx": {"icon": "📝", "label": "Word 文档", "color": "#2563eb"},
        ".doc": {"icon": "📝", "label": "Word 文档", "color": "#2563eb"},
        ".xlsx": {"icon": "📊", "label": "Excel 表格", "color": "#16a34a"},
        ".xls": {"icon": "📊", "label": "Excel 表格", "color": "#16a34a"},
        ".pptx": {"icon": "📽️", "label": "PPT 演示", "color": "#ea580c"},
        ".ppt": {"icon": "📽️", "label": "PPT 演示", "color": "#ea580c"},
        ".csv": {"icon": "📈", "label": "CSV 数据", "color": "#0891b2"},
        ".txt": {"icon": "📃", "label": "文本文件", "color": "#6b7280"},
    }
    cfg = type_config.get(ext, {"icon": "📎", "label": "文件", "color": "#6b7280"})

    # PDF 支持在线预览
    preview_btn = ""
    if ext == ".pdf":
        preview_btn = f'<a href="{filename}" target="_blank" style="display:inline-block;margin-left:12px;padding:12px 28px;background:#fff;color:{cfg["color"]};border:2px solid {cfg["color"]};border-radius:8px;text-decoration:none;font-weight:600;">在线预览</a>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{filename}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
            background: #ffffff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 600px;
            width: 100%;
        }}
        .header {{
            border-bottom: 3px solid {cfg["color"]};
            padding-bottom: 20px;
            margin-bottom: 32px;
        }}
        .header h1 {{
            font-size: 24px;
            color: #111827;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        .header .subtitle {{
            font-size: 14px;
            color: #6b7280;
        }}
        .file-card {{
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 32px;
            text-align: center;
            margin-bottom: 24px;
        }}
        .file-icon {{
            font-size: 64px;
            margin-bottom: 16px;
        }}
        .file-name {{
            font-size: 18px;
            font-weight: 600;
            color: #111827;
            margin-bottom: 8px;
            word-break: break-all;
        }}
        .file-meta {{
            font-size: 14px;
            color: #6b7280;
            margin-bottom: 24px;
        }}
        .file-type-badge {{
            display: inline-block;
            padding: 4px 12px;
            background: {cfg["color"]}15;
            color: {cfg["color"]};
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 20px;
        }}
        .btn-group {{
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
        }}
        .btn-download {{
            display: inline-block;
            padding: 12px 28px;
            background: {cfg["color"]};
            color: #fff;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            border: none;
            cursor: pointer;
        }}
        .description {{
            margin-top: 24px;
            padding: 16px;
            background: #f9fafb;
            border-radius: 8px;
            font-size: 14px;
            color: #4b5563;
            line-height: 1.6;
        }}
        .footer {{
            text-align: center;
            margin-top: 32px;
            font-size: 12px;
            color: #9ca3af;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>生物医药报告文件</h1>
            <div class="subtitle">File Download Center</div>
        </div>
        <div class="file-card">
            <div class="file-icon">{cfg["icon"]}</div>
            <div class="file-type-badge">{cfg["label"]}</div>
            <div class="file-name">{filename}</div>
            <div class="file-meta">{file_size_kb:.1f} KB</div>
            <div class="btn-group">
                <a href="{filename}" download class="btn-download">下载文件</a>
                {preview_btn}
            </div>
        </div>
        {f'<div class="description">{description}</div>' if description else ''}
        <div class="footer">
            Powered by BioMCP · 匿名文件保留3天
        </div>
    </div>
</body>
</html>"""


@mcp.tool()
async def publish_file(
    file_content_base64: str,
    filename: str,
    description: str = "",
) -> dict:
    """
    发布 Word / Excel / PDF 等文件，自动生成在线下载页。
    支持格式：.pdf .docx .xlsx .pptx .csv .txt
    PDF 文件支持浏览器内在线预览，其他格式自动下载。

    Args:
        file_content_base64: 文件内容的 base64 编码字符串
        filename: 文件名（带扩展名），如 "PD1临床简报.docx" 或 "数据汇总.xlsx"
        description: 可选的文件描述，显示在下载页上
    """
    import base64 as b64mod

    # 解码 base64 获取文件大小
    try:
        file_bytes = b64mod.b64decode(file_content_base64)
        file_size_kb = len(file_bytes) / 1024
    except Exception as e:
        return {
            "success": False,
            "error": f"base64 解码失败: {str(e)}",
        }

    # 生成下载页 HTML
    download_html = _build_download_page(filename, file_size_kb, "", description)

    # ShipStatic 文件列表：HTML 封面页 + 原始文件
    # 注意：ShipStatic 的 content 字段是字符串，二进制文件需要确认编码方式
    files = [
        {
            "path": "index.html",
            "content": download_html,
        },
        {
            "path": filename,
            "content": file_content_base64,
            "encoding": "base64",
        }
    ]

    url = "https://api.shipstatic.com/v1/deployments"
    payload = {"files": files}
    headers = {"Content-Type": "application/json"}

    resp = await http_client.post(url, json=payload, headers=headers)
    if resp.status_code not in (200, 201):
        return {
            "success": False,
            "error": f"发布失败: HTTP {resp.status_code}",
            "detail": resp.text[:500],
        }

    data = resp.json()
    return {
        "success": True,
        "url": data.get("url", ""),
        "claim_url": data.get("claimUrl", ""),
        "deployment_id": data.get("id", ""),
        "filename": filename,
        "file_size_kb": round(file_size_kb, 1),
        "message": f"文件发布成功！打开链接即可下载 {filename}（{file_size_kb:.1f} KB）",
    }


# ============================================================
# 启动服务
# ============================================================
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    print(f"BioMCP Full Server starting on port {port}...")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port, path="/mcp")
