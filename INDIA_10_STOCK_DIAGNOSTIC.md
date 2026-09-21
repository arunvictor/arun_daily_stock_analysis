# INDIA 10-Stock Diagnostic — why only 2 stocks appeared in report_20260921.md

Investigation only. No source code or `.env` modified. No fixes applied.
Log evidence: `logs/stock_analysis_debug_20260921.log` (run 2026-09-21 02:08 → 04:42).

## 1. Requested list vs. what was passed to main.py

`.env` line 9:
```
STOCK_LIST=RELIANCE.NS,TCS.NS,INFY.NS,HDFCBANK.NS,ICICIBANK.NS,SBIN.NS,BHARTIARTL.NS,LT.NS,SUNPHARMA.NS,ITC.NS
```

`main.py` passed the exact same 10 codes to the pipeline (log line 12, main.py:1585):
```
['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'SBIN.NS', 'BHARTIARTL.NS', 'LT.NS', 'SUNPHARMA.NS', 'ITC.NS']
```

All 10 stocks were accepted by the pipeline. None was filtered as unsupported or duplicated.
- Pipeline banner: `===== 开始分析 10 只股票 =====` (pipeline.py:3471)
- Stock list: `RELIANCE.NS, TCS.NS, INFY.NS, HDFCBANK.NS, ICICIBANK.NS, SBIN.NS, BHARTIARTL.NS, LT.NS, SUNPHARMA.NS, ITC.NS` (pipeline.py:3472)

## 2. Stock list parsing

Parsing is fine — all 10 codes reached the per-stock analysis stage
(`========== 开始分析 <STOCK> ==========`, pipeline.py:3328, appears for all 10).

## 3. Per-stock processing / data fetch / LLM analysis

- **All 10 stocks reached analysis and had market data fetched** (partial/fallback quality; the akshare primary provider failed for all 10, data came from a fallback source).
- **LLM analysis completed for only 2 stocks** (RELIANCE, ITC).
- **LLM analysis failed for the other 8** with an Ollama timeout.

LLM success (analyzer.py:3969 / pipeline.py:3371):
- `RELIANCE.NS` → "分析完成: 持有, 评分 50" (03:25:07)
- `ITC.NS` → "分析完成: 持有, 评分 50" (04:42:33)

LLM failure (analyzer.py:3975 ERROR / pipeline.py:3384 WARNING / pipeline.py:3561 WARNING):
- All 8 failed with:
  `All LLM models failed (tried 1 model(s)). Last error: APIConnectionError: litellm.APIConnectionError: OllamaException - litellm.Timeout: Connection timed out after 600.0 seconds.`
- Logged as `分析未成功` and `分析结果标记为失败，不计入汇总`.

## 4. Pipeline summary (pipeline.py:3606)

```
===== 分析结果 =====
成功: 2, 失败: 8
```

## 5. Why the report shows only 2 stocks

Reports intentionally contain only stocks whose analysis **succeeded**
(pipeline.py:3552–3564):
```python
if result and result.success:
    results.append(result)
elif result and not result.success:
    logger.warning(f"[{code}] 分析结果标记为失败，不计入汇总: ...")
```
The 8 LLM-failed stocks were excluded from `results`, so the report generator
only rendered RELIANCE and ITC. Report header confirms: `共分析 2 只股票`.

This is **not** a stock-list parsing bug, and **not** an India/NSE mapping bug.
All 10 stocks were correctly recognized and processed; 8 were dropped because
their LLM analysis timed out.

## 6. Final status of every stock

| Stock | Reached analysis? | Data fetched? | LLM analysis? | Final status | Failure reason |
|-------|-------------------|---------------|---------------|--------------|----------------|
| RELIANCE.NS | Yes (pipeline.py:3328) | Yes (fallback/partial) | Yes — "持有, 评分 50" | Included in report | none |
| TCS.NS | Yes | Yes (fallback/partial) | No — failed | Excluded (not in report) | LLM timeout (Ollama qwen3:4b, 600s) |
| INFY.NS | Yes | Yes (fallback/partial) | No — failed | Excluded | LLM timeout (Ollama qwen3:4b, 600s) |
| HDFCBANK.NS | Yes | Yes (fallback/partial) | No — failed | Excluded | LLM timeout (Ollama qwen3:4b, 600s) |
| ICICIBANK.NS | Yes | Yes (fallback/partial) | No — failed | Excluded | LLM timeout (Ollama qwen3:4b, 600s) |
| SBIN.NS | Yes | Yes (fallback/partial) | No — failed | Excluded | LLM timeout (Ollama qwen3:4b, 600s) |
| BHARTIARTL.NS | Yes | Yes (fallback/partial) | No — failed | Excluded | LLM timeout (Ollama qwen3:4b, 600s) |
| LT.NS | Yes | Yes (fallback/partial) | No — failed | Excluded | LLM timeout (Ollama qwen3:4b, 600s) |
| SUNPHARMA.NS | Yes | Yes (fallback/partial) | No — failed | Excluded | LLM timeout (Ollama qwen3:4b, 600s) |
| ITC.NS | Yes | Yes (fallback/partial) | Yes — "持有, 评分 50" | Included in report | none |

## 7. Root cause summary

The 8 missing stocks were **not** skipped before analysis and were **not**
misparsed. Every one of the 10 stocks reached analysis with market data
available. The single reason they are absent from the report is that their
**LLM analysis failed with a timeout** against the configured model
`ollama/qwen3:4b` (`LITELLM_MODEL`, `.env`), returning
`litellm.Timeout: Connection timed out after 600.0 seconds`.

Secondary observation: the primary A-share-oriented provider (akshare) failed
for all 10 NSE codes (Connection aborted / RemoteDisconnected / NoneType),
and data was served by a fallback source with partial quality
(report marks `quote: fallback`, `technical: partial`). This did not block
analysis, but is a contributing fragility for NSE stocks.

Note: final `main.py:765` line (`processed=0 saved=0 completed=0 ...`) is a
separate scheduler summary path and is not the count used to build the report.