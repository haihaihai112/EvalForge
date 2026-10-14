const $ = (q, root = document) => root.querySelector(q);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const paths = {
  dashboard:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  data:'M4 6c0-4 16-4 16 0s-16 4-16 0zm0 0v6c0 4 16 4 16 0V6M4 12v6c0 4 16 4 16 0v-6',
  flask:'M9 3h6M10 3v6L4 19a1 1 0 0 0 1 2h14a1 1 0 0 0 1-2L14 9V3M8 14h8',
  trace:'M4 4v16h16M4 8h12M8 12h12M12 16h8',
  settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.5 1.5M17 17l1.4 1.4M5.6 18.4l1.5-1.5M17 7l1.4-1.4',
  plus:'M12 5v14M5 12h14', check:'m5 12 4 4L19 6', arrow:'M5 12h14m-5-5 5 5-5 5',
  clock:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v5l3 2',
  shield:'m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3m-4 9 3 3 5-6',
  upload:'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6',
  download:'M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4',
  book:'M4 3h13l3 3v15H4V3m4 5h7M8 12h8M8 16h6',
  info:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 11v6M12 7v1',
  play:'m8 4 12 8-12 8V4', coins:'M4 6c0-4 16-4 16 0s-16 4-16 0zm0 0v5c0 4 16 4 16 0V6M4 11v6c0 4 16 4 16 0v-6',
  file:'M6 2h8l4 4v16H6V2m8 0v5h4M9 12h6M9 16h6', search:'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14m5 12 6 6'
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.file}"/></svg>`;
const pct = v => v == null ? '—' : `${(v * 100).toFixed(1)}%`;
const ms = v => v == null ? '—' : v < 1000 ? `${v.toFixed(1)} ms` : `${(v/1000).toFixed(2)} s`;
const money = v => v == null ? '未提供' : v === 0 ? '$0.0000' : `$${v.toFixed(6)}`;
const date = v => v ? new Date(v).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}) : '—';
const categoryNames = {factual:'事实题',scenario:'场景题',multi_hop:'多跳推理',false_premise:'错误前提',unanswerable:'不可回答'};
const statuses = {queued:'等待中',running:'执行中',completed:'已完成',failed:'运行失败',interrupted:'已中断',approved:'已确认',candidate:'待审阅'};
const state = {page:'overview', overview:null, documents:[], datasets:[], runs:[], config:{}, dataset:null, run:null, filter:'all', traceId:'', spans:[], busy:false, polling:false};
let toastTimer;
function toast(text, error=false){const el=$('#toast');el.textContent=text;el.classList.add('visible');el.style.background=error?'#a63d52':'#203952';clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('visible'),error?8000:4500);}
async function api(path, options={}){
  const response=await fetch('/api'+path,options);
  let value;try{value=await response.json();}catch{throw new Error(`服务返回异常（${response.status}）`);}
  if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));
  return value;
}
const post=(path,body)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
const badge=(status)=>`<span class="badge ${['failed','interrupted'].includes(status)?'error':['running','queued','candidate'].includes(status)?'warn':''}">${esc(statuses[status]||status)}</span>`;
const mode=(v)=>`<span class="badge ${v==='demo'?'warn':'blue'}">${v==='demo'?'演示':'真实模型'}</span>`;
const empty=text=>`<div class="empty">${icon('data')}<div>${esc(text)}</div></div>`;
const score=v=>v==null?'<span class="subtext">未评分</span>':`<span class="${v<.8?'negative':'positive'}">${pct(v)}</span><span class="score-bar"><i style="width:${Math.max(0,Math.min(100,v*100))}%"></i></span>`;
function shell(content){
  const names={overview:'质量总览',datasets:'测试集管理',runs:'评测工作台',traces:'链路审计'};
  return `<div class="shell"><aside class="sidebar"><a href="#overview" class="brand"><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span><span><strong>EvalForge</strong><small>Agent evaluation studio</small></span></a><p class="nav-caption">工作空间</p><nav>${[['overview','dashboard'],['datasets','data'],['runs','flask'],['traces','trace']].map(([key,img])=>`<a href="#${key}" class="nav-link ${state.page===key?'active':''}" ${state.page===key?'aria-current="page"':''}>${icon(img)}${names[key]}${key==='datasets'?`<em>${state.datasets.length}</em>`:''}</a>`).join('')}</nav><div class="sidebar-footer"><div><span class="local-dot"></span>本地 SQLite 已连接</div><div>个人工作区 / v0.1.0</div><div>让每一个回答，都有据可查。</div></div></aside><div class="workspace"><header class="topbar"><div class="breadcrumb">个人工作区 <span>/</span> <b>${names[state.page]}</b></div><div class="toolbar"><span class="local-pill"><span class="local-dot"></span>本地运行</span><a href="/docs" target="_blank" rel="noopener">API 文档</a><button class="quiet small" data-action="settings">${icon('settings')}配置</button><div class="avatar" aria-label="个人工作区">EF</div></div></header><main class="main">${content}<div class="bottom-note">EvalForge · 独立实现的评测与追踪内核<br>本地数据、本地审计，真实模式由你配置模型与 Agent。</div></main></div></div>`;
}
function heading(title,subtitle,actions=''){return `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div>${actions?`<div class="heading-actions">${actions}</div>`:''}</div>`;}
function notice(modeName='demo'){return modeName==='demo'?`<div class="notice">${icon('info')}<span>当前为演示数据。两个 LogiGraph 版本是带已知错误的本地 fixture，裁判使用字符串核验；图表不代表真实向量检索或 GraphRAG 性能。</span></div>`:`<div class="notice">${icon('shield')}<span>真实模式：逐声明由配置的模型核验；得分代表所给证据支持程度。请结合人工审阅与错误率判断质量。</span></div>`;}
function stat(label,value,unit,note,img){return `<article class="stat"><div class="stat-top">${label}${icon(img)}</div><div class="stat-value">${value}<small>${unit}</small></div><div class="stat-note">${note}</div></article>`;}
function radar(summaries){
  const entries=Object.entries(summaries||{}).slice(0,2), center=[160,137], radius=88;
  const axes=[{label:'证据召回',key:'recall'},{label:'忠实度',key:'faithfulness'},{label:'响应效率',key:'p95_ms',inverse:5000},{label:'成本效率',key:'cost_usd',inverse:.02}];
  const xy=(i,r)=>[center[0]+Math.sin(i*Math.PI/2)*r,center[1]-Math.cos(i*Math.PI/2)*r];
  const point=(i,r)=>xy(i,r).join(',');
  let svg=`<svg class="radar" role="img" aria-label="版本对比雷达图：召回和忠实度越高越好，延迟及成本经反向归一化" viewBox="0 0 320 275">`;
  for(let level=1;level<=4;level++)svg+=`<polygon points="${axes.map((a,i)=>point(i,radius*level/4)).join(' ')}" fill="${level%2?'#f8fafc':'none'}" stroke="#e0e8ef" stroke-width="1"/>`;
  axes.forEach((a,i)=>{const p=xy(i,radius+23);svg+=`<line x1="160" y1="137" x2="${xy(i,radius)[0]}" y2="${xy(i,radius)[1]}" stroke="#e5ebf0"/><text x="${p[0]}" y="${p[1]+4}" text-anchor="middle" fill="#77889c" font-size="10.5">${a.label}</text>`;});
  entries.forEach(([name,values],j)=>{
    const color=j?'#087e8b':'#7971c5';
    const norm=axes.map(a=>values[a.key]==null?null:a.inverse?Math.max(0,Math.min(1,1-values[a.key]/a.inverse)):Math.max(0,Math.min(1,values[a.key])));
    // A polygon would imply a measured value at every axis. Missing axes render as points only.
    if(norm.every(v=>v!==null))svg+=`<polygon points="${norm.map((v,i)=>point(i,radius*v)).join(' ')}" fill="${color}" fill-opacity=".09" stroke="${color}" stroke-width="1.8"/>`;
    norm.forEach((v,i)=>{if(v!==null){const p=xy(i,radius*v);svg+=`<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="${color}"><title>${esc(name)} ${axes[i].label}</title></circle>`;}});
  });
  svg+='</svg>';
  return `<div class="chart-layout">${svg}<div>${entries.map(([name,value],i)=>`<div class="chart-key"><div class="legend-version"><i class="key-dot" style="background:${i?'#087e8b':'#7971c5'}"></i>${esc(name.replace(' · 演示',''))}</div><div class="legend-sub">${value.count} 次调用 · ${value.scored_count} 题有评分</div></div>`).join('')}<div class="legend-sub">向外代表指标更优<br>缺失值仅绘制有效点</div></div></div>`;
}
function comparison(summaries){const es=Object.entries(summaries||{}).slice(0,2);if(!es.length)return empty('运行评测后查看版本对比');const rows=[['证据召回 ↑','recall',pct],['忠实度 ↑','faithfulness',pct],['P95 响应延迟 ↓','p95_ms',ms],['单次 Agent 成本 ↓','cost_usd',money],['拒答准确率 ↑','refusal_accuracy',pct],['Agent 错误率 ↓','error_rate',pct]];return `<table class="metric-compare"><thead><tr><th>原始指标</th>${es.map(([name])=>`<th>${esc(name.replace(' · 演示',''))}</th>`).join('')}</tr></thead><tbody>${rows.map(([label,key,fmt])=>`<tr><td>${label}</td>${es.map(([,v])=>`<td>${fmt(v[key])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;}
function overviewPage(){
  const data=state.overview, latest=data?.latest, entries=Object.entries(latest?.summaries||{}), best=entries[entries.length-1]?.[1], first=entries[0]?.[1];
  const diff=best?.faithfulness!=null&&first?.faithfulness!=null?(best.faithfulness-first.faithfulness)*100:null;
  let result=heading('质量总览','从测试集到事实声明，追踪 Agent 质量的每一次变化。',`<span class="mode-label">${latest?.mode==='live'?'真实运行':'演示工作区'}</span><a href="#runs"><button class="primary">${icon('plus')}新建评测</button></a>`)+notice(latest?.mode);
  result+=`<section class="stats">${stat('已确认测试题',state.datasets.filter(d=>d.review_status==='approved').reduce((n,d)=>n+d.case_count,0),'题',`${state.datasets.length} 个测试集 · ${state.documents.length} 份文档`,'data')}${stat('最新版本忠实度',best?.faithfulness==null?'—':(best.faithfulness*100).toFixed(1),'%',diff==null?'暂无可对比的运行':`<span class="${diff>=0?'positive':'negative'}">${diff>=0?'+':''}${diff.toFixed(1)} 个百分点</span> · 同一测试集`,'shield')}${stat('P95 响应延迟',best?.p95_ms==null?'—':best.p95_ms.toFixed(1),'ms',latest?.mode==='demo'?'本地 fixture 实测 · 不含裁判耗时':'Agent 调用实测 · 不含裁判耗时','clock')}${stat('单次 Agent 成本',best?.cost_usd==null?'—':`$${best.cost_usd.toFixed(4)}`,'',latest?.mode==='demo'?'演示模式无模型计费':'Agent 上报成本 · 未含裁判','coins')}</section>`;
  result+=`<div class="content-grid"><section class="panel"><div class="panel-head"><h2>${icon('flask')}版本质量对比</h2><small>${latest?esc(latest.dataset_name):'等待首次评测'}</small></div>${latest?radar(latest.summaries)+comparison(latest.summaries):empty('选择测试集，开始第一轮评测')}<div class="chart-foot">固定归一化：延迟上限 5,000 ms，成本上限 $0.02；超限显示 0。原始值见表格。</div></section><section class="panel"><div class="panel-head"><h2>${icon('clock')}最近评测</h2><a href="#runs" class="subtext">查看全部</a></div>${data?.recent_runs?.length?data.recent_runs.slice(0,4).map(run=>`<div class="run-entry" tabindex="0" role="button" data-action="select-run" data-id="${esc(run.id)}"><div class="run-glyph">${icon('check')}</div><div><strong>${esc(run.name)}</strong><p>${date(run.created_at)} · ${run.mode==='demo'?'演示':'真实'} · top-k ${run.top_k}</p><p>${esc(run.dataset_name)}</p></div>${badge(run.status)}</div>`).join(''):empty('还没有评测记录')}<div class="run-details">${icon('shield')} 严格证据计分<div class="divider"></div>只有原文支持的声明才计分；证据不足与直接矛盾分别展示。<br>空声明、裁判错误与缺失成本保留独立状态。</div></section></div>`;
  const samples=state.run?.id===latest?.id?state.run.results:[];
  result+=`<section class="panel"><div class="panel-head"><h2>${icon('trace')}值得审阅的回答</h2><a href="#runs" class="subtext">进入评测工作台</a></div>${samples.length?resultsTable(samples.filter(r=>r.evaluation?.score<1&&r.evaluation?.score!=null).slice(0,5),true):empty('暂无已加载的回答；进入工作台查看逐题结果')}</section>`;
  return result;
}
function datasetsPage(){
  const chosen=state.dataset;
  return heading('测试集管理','导入制度原文，生成带来源证据的候选题，再确认用于回归。')+`<div class="setup-grid"><section class="panel"><div class="panel-head"><h2>${icon('upload')}从 SOP 生成测试集</h2></div><div class="panel-body"><div class="upload-area" id="drop-zone">${icon('upload')}<p>将物流 SOP 拖入这里</p><small>TXT / MD / PDF / DOCX，最大 8 MB</small><button data-action="upload" ${state.busy?'disabled':''}>选择文档</button><input type="file" id="file-input" accept=".txt,.md,.pdf,.docx" class="sr-only" aria-label="上传 SOP 文档"></div><div class="field"><label for="document-select">来源文档</label><select id="document-select">${state.documents.map(d=>`<option value="${esc(d.id)}">${esc(d.name)} · ${d.chunk_count} 条款</option>`).join('')}</select></div><div class="two-fields"><div class="field"><label for="case-count">题目数量</label><input id="case-count" type="number" min="1" max="50" value="50"></div><div class="field"><label for="generation-mode">生成模式</label><select id="generation-mode"><option value="demo">演示模板</option><option value="live">真实模型</option></select></div></div><div class="notice warning">演示模板用于体验流程；真实模型负责生成领域语义题。所有新测试集均需人工确认。</div><button class="primary full" data-action="generate" ${state.busy||!state.documents.length?'disabled':''}>${icon('flask')}${state.busy?'正在处理，请稍候…':'生成候选测试集'}</button></div></section><div><section class="panel"><div class="panel-head"><h2>${icon('data')}我的测试集 <span class="filter-count">${state.datasets.length}</span></h2><small>JSON 快照可导出</small></div>${state.datasets.length?state.datasets.map(d=>`<div class="dataset-tile"><div class="dataset-icon">${icon('data')}</div><div><h3>${esc(d.name)}</h3><p>${d.case_count} 题 · ${date(d.created_at)} ${mode(d.mode)}</p><p>内容指纹 <span class="mono">${esc(d.fingerprint.slice(0,12))}</span> ${badge(d.review_status)}</p></div><div class="tile-actions"><button class="small" data-action="view-dataset" data-id="${esc(d.id)}">审阅题目</button><a class="link-button" href="/api/datasets/${esc(d.id)}/export" download>导出</a></div></div>`).join(''):empty('上传文档并生成第一个测试集')}</section>${chosen?`<section class="panel space-top"><div class="panel-head"><h2>${esc(chosen.name)}</h2>${chosen.review_status==='candidate'?`<button class="primary small" data-action="approve" data-id="${esc(chosen.id)}">确认整份测试集</button>`:badge('approved')}</div><div class="notice" style="margin:15px">逐题检查答案与证据，重点审查多跳题是否确实需要两条规则、错误前提题是否被纠正。确认按钮表示你已审阅整份数据集。</div><div class="table-wrap"><table class="data"><thead><tr><th>问题</th><th>类型</th><th>证据</th><th></th></tr></thead><tbody>${chosen.cases.map(c=>`<tr class="clickable" tabindex="0" data-action="golden-detail" data-id="${esc(c.id)}"><td class="question-cell">${esc(c.question)}</td><td><span class="badge blue">${categoryNames[c.category]||esc(c.category)}</span></td><td>${c.expected_chunk_ids.length} 条</td><td>${icon('arrow')}</td></tr>`).join('')}</tbody></table></div></section>`:''}</div></div>`;
}
function evaluationStatus(r){if(r.status!=='ok')return '<span class="badge error">Agent 异常</span>';if(r.evaluation?.status==='evaluation_error')return '<span class="badge error">裁判异常</span>';if(r.evaluation?.status==='no_claims')return '<span class="badge neutral">无事实声明</span>';return r.evaluation?.score===1?'<span class="badge">全部有据</span>':'<span class="badge warn">存在无据声明</span>';}
function resultsTable(rows,compact=false){
  if(!rows.length)return empty('当前筛选条件下没有回答');
  return `<div class="table-wrap"><table class="data"><thead><tr><th>测试问题</th><th>版本</th><th>忠实度</th><th>${compact?'状态':'耗时'}</th><th>详情</th></tr></thead><tbody>${rows.map(r=>`<tr class="clickable" tabindex="0" data-action="result-detail" data-id="${esc(r.case_id)}" data-version="${esc(r.version)}"><td><div class="question-cell">${esc(r.question)}</div><span class="subtext">${esc(r.case_id)} · ${categoryNames[r.category]||esc(r.category)}</span></td><td><span class="badge ${r.version.includes('v2')?'blue':'neutral'}">${esc(r.version.replace(' · 演示',''))}</span></td><td>${score(r.evaluation?.score)}</td><td>${compact?evaluationStatus(r):ms(r.latency_ms)}</td><td><button class="link-button" data-action="result-detail" data-id="${esc(r.case_id)}" data-version="${esc(r.version)}">查看证据</button></td></tr>`).join('')}</tbody></table></div>`;
}
function runsPage(){
  const run=state.run, complete=run?.status==='completed', running=['queued','running'].includes(run?.status);
  let result=heading('评测工作台','固定测试集与评估口径，对两个 Agent 版本进行逐题回归。');
  result+=`<div class="setup-grid"><section class="panel"><div class="panel-head"><h2>${icon('flask')}新建版本回归</h2></div><div class="panel-body"><div class="field"><label for="run-name">运行名称</label><input id="run-name" value="LogiGraph 双版本回归" maxlength="100"></div><div class="field"><label for="dataset-select">测试集</label><select id="dataset-select">${state.datasets.filter(d=>d.review_status==='approved').map(d=>`<option value="${esc(d.id)}">${esc(d.name)} (${d.case_count} 题)</option>`).join('')}</select><small>仅显示已确认的测试集。<a href="#datasets">去审阅</a></small></div><div class="two-fields"><div class="field"><label for="run-mode">执行模式</label><select id="run-mode"><option value="demo">离线演示</option><option value="live">真实 Agent</option></select></div><div class="field"><label for="top-k">召回 top-k</label><input id="top-k" type="number" min="1" max="20" value="5"></div></div><div class="notice">${icon('info')}真实模式需在 .env 中配置模型裁判和两个 Agent 的 HTTP 地址。</div><button class="primary full" data-action="start-run" ${running||state.busy||!state.datasets.some(d=>d.review_status==='approved')?'disabled':''}>${icon('play')}${running?'评测执行中…':'开始版本回归'}</button></div><div class="chart-foot">按同一测试题交替调用两个版本。延迟统计只覆盖 Agent 调用，裁判成本单独汇总。</div></section><div><section class="panel"><div class="panel-head"><h2>运行记录</h2><label class="sr-only" for="run-select">选择运行记录</label><select id="run-select" style="width:65%">${state.runs.map(r=>`<option value="${esc(r.id)}" ${r.id===run?.id?'selected':''}>${esc(r.name)} · ${date(r.created_at)}</option>`).join('')}</select></div>${run?`<div class="run-strip"><div><strong>${esc(run.name)} ${mode(run.mode)}</strong><small>${esc(run.dataset_name)} · top-k ${run.top_k} · ${esc(run.judge_model)}</small><div class="progress"><i style="width:${run.progress}%"></i></div><small>${run.progress}% · ${run.results.length} 次调用已完成</small></div><div>${badge(run.status)} <a class="link-button" href="/api/runs/${esc(run.id)}/export" download>导出快照</a></div></div>${run.error?`<div class="error-box">${esc(run.error)}</div>`:''}${comparison(run.summaries)}<div class="chart-foot">${complete?'已完成':'当前已完成部分'} · ${Object.values(run.summaries).reduce((n,s)=>n+s.evaluation_error_count,0)} 次裁判异常 · ${Object.values(run.summaries).reduce((n,s)=>n+s.no_claims_count,0)} 次无声明 · 裁判总成本 ${Object.values(run.summaries).every(s=>s.judge_cost_usd!=null)?money(Object.values(run.summaries).reduce((n,s)=>n+s.judge_cost_usd,0)):'未提供'}<br>数据集内容指纹 <span class="mono">${esc(run.dataset_fingerprint?.slice(0,16))}</span> · ${esc(run.metric_version)}</div>`:empty('确认测试集后，开始第一轮回归')}</section></div></div>`;
  if(run){
    let rows=run.results;
    if(state.filter==='risk')rows=rows.filter(r=>r.evaluation?.score!=null&&r.evaluation.score<1);
    if(state.filter==='pass')rows=rows.filter(r=>r.evaluation?.score===1);
    if(state.filter==='refusal')rows=rows.filter(r=>r.expected_refusal);
    if(state.filter==='error')rows=rows.filter(r=>r.status!=='ok'||r.evaluation?.status==='evaluation_error');
    result+=`<section class="panel space-top"><div class="panel-head"><h2>${icon('shield')}逐题结果 <span class="filter-count">${run.results.length}</span></h2><small>点击回答，检查声明与证据</small></div><div class="filters">${[['all','全部回答'],['risk','存在无据'],['pass','全部有据'],['refusal','拒答测试'],['error','执行异常']].map(([id,label])=>`<button class="filter ${id===state.filter?'active':''}" data-action="filter" data-id="${id}">${label}</button>`).join('')}</div>${resultsTable(rows)}</section>`;
  }
  return result;
}
function tracesPage(){
  const traces=new Map();for(const span of state.spans){if(!traces.has(span.trace_id))traces.set(span.trace_id,[]);traces.get(span.trace_id).push(span);}
  let traceContent='';
  if(state.traceId){
    const spans=[...state.spans].sort((a,b)=>a.started_at.localeCompare(b.started_at));
    const byId=new Map(spans.map(s=>[s.span_id,s]));
    const depth=s=>{let n=0,p=s;const seen=new Set();while(p.parent_span_id&&byId.has(p.parent_span_id)&&n<10&&!seen.has(p.parent_span_id)){seen.add(p.parent_span_id);p=byId.get(p.parent_span_id);n++;}return n;};
    const max=Math.max(1,...spans.map(s=>s.duration_ms));const start=Math.min(...spans.map(s=>new Date(s.started_at).getTime()));
    traceContent=spans.map(s=>`<div class="trace-line" tabindex="0" role="button" data-action="span-detail" data-id="${esc(s.span_id)}"><div class="trace-name" style="padding-left:${depth(s)*15}px">${icon(s.kind==='judge'?'shield':s.kind==='agent'?'flask':'trace')}<span>${esc(s.name)}<br><span class="subtext">${esc(s.kind)} ${s.status==='error'?'· 异常':''}</span></span></div><div class="trace-track"><i style="left:${Math.min(85,(new Date(s.started_at).getTime()-start)/max*85)}%;width:${Math.min(100,Math.max(1,s.duration_ms/max*85))}%"></i></div><div class="trace-duration">${ms(s.duration_ms)}</div></div>`).join('')||empty('此 Trace 没有记录，请检查 ID');
  }else{
    const roots=[...traces.entries()].map(([id,spans])=>({id,spans,root:spans.find(s=>!s.parent_span_id)||spans[spans.length-1]})).slice(0,80);
    traceContent=roots.length?`<div class="table-wrap"><table class="data"><thead><tr><th>Trace / 运行</th><th>版本</th><th>Span 数量</th><th>开始时间</th><th></th></tr></thead><tbody>${roots.map(({id,spans,root})=>`<tr class="clickable" tabindex="0" data-action="select-trace" data-id="${esc(id)}"><td><span class="mono">${esc(id.slice(0,18))}</span><div class="subtext">${esc(root.attributes.case_id||root.name)}</div></td><td>${esc(root.attributes.version||'—')}</td><td>${spans.length}</td><td>${date(root.started_at)}</td><td><button class="link-button" data-action="select-trace" data-id="${esc(id)}">查看链路</button></td></tr>`).join('')}</tbody></table></div>`:empty('执行一次回归后，这里将展示实际记录的链路');
  }
  return heading('链路审计','沿着执行链路检查 Prompt、工具输入输出、Token 用量和异常。',`<button data-action="refresh-traces">${icon('clock')}刷新链路</button>`)+`<section class="panel"><div class="panel-head"><h2>${icon('trace')}${state.traceId?'单次调用链路':'最近执行链路'}</h2>${state.traceId?'<button class="small" data-action="all-traces">返回列表</button>':'<small>读取最近 2,000 个 Span，展示最多 80 条链路</small>'}</div><div class="panel-body"><div class="search-row"><label class="sr-only" for="trace-search">完整 Trace ID</label><input id="trace-search" placeholder="输入完整 Trace ID，查找执行链路" value="${esc(state.traceId)}"><button class="primary" data-action="search-trace">${icon('search')}查询</button></div></div>${traceContent}<div class="trace-hint">Token 与成本记录在各调用自身的 usage 字段中。父子耗时包含关系不能相加；本地装饰器不自动捕获远程 Agent 内部步骤，远程服务可使用同一 SDK 插桩。</div></section>`;
}
function render(){ $('#app').innerHTML=shell(({overview:overviewPage,datasets:datasetsPage,runs:runsPage,traces:tracesPage}[state.page]||overviewPage)()); }
async function refresh(){
  const [overview,documents,datasets,runs,config]=await Promise.all([api('/overview'),api('/documents'),api('/datasets'),api('/runs'),api('/config')]);
  Object.assign(state,{overview,documents,datasets,runs,config});
  if(!state.run&&runs.length)state.run=await api('/runs/'+runs[0].id);
  if(state.page==='traces')await loadTraces();
}
async function loadTraces(){state.spans=await api('/spans'+(state.traceId?'?trace_id='+encodeURIComponent(state.traceId):''));}
function showDetail(html){$('#detail-content').innerHTML=html;if(!$('#detail').open)$('#detail').showModal();}
function goldenDetail(id){const c=state.dataset?.cases.find(c=>c.id===id);if(!c)return;showDetail(`<h2>${esc(c.question)}</h2><div class="detail-meta"><span class="badge blue">${categoryNames[c.category]}</span>${badge(c.review_status)}</div><h3>候选标准答案</h3><p>${esc(c.expected_answer)}</p><h3>来源证据</h3>${c.evidence.map(e=>`<div class="evidence"><div class="mono">${esc(e.chunk_id)}</div>${esc(e.quote)}</div>`).join('')||'<p>不可回答题：制度未提供答案，应拒答或请求澄清。</p>'}<h3>审阅要点</h3><p>检查答案是否保留数字、条件与否定；确认引用支持整个答案，而非仅有词语重合。</p>`);}
function resultDetail(caseId,version){
  const r=state.run?.results.find(r=>r.case_id===caseId&&r.version===version);if(!r)return;
  const byId=new Map((r.evaluation?.verdicts||[]).map(v=>[v.claim_id,v]));
  showDetail(`<h2>${esc(r.question)}</h2><div class="detail-meta"><span class="badge blue">${esc(r.version)}</span>${evaluationStatus(r)}<span class="badge neutral">${ms(r.latency_ms)}</span></div><h3>Agent 回答</h3><p>${esc(r.answer||r.error||'无回答')}</p><h3>标准答案</h3><p>${esc(r.expected_answer)}</p><h3>忠实度 ${pct(r.evaluation?.score)}</h3>${r.evaluation?.error?`<div class="error-box">${esc(r.evaluation.error)}</div>`:''}${(r.evaluation?.claims||[]).map(c=>{const v=byId.get(c.id);return `<div class="claim"><span class="badge ${v?.label==='supported'?'':v?.label==='contradicted'?'error':'warn'}">${({supported:'有据支持',unsupported:'证据不足',contradicted:'与原文矛盾'})[v?.label]||'未核验'}</span><p>${esc(c.text)}</p><div class="subtext">${esc(v?.reason||'裁判未返回有效判定')}</div>${(v?.evidence||[]).map(e=>`<div class="evidence"><div class="mono">${esc(e.chunk_id)}</div>${esc(e.quote)}</div>`).join('')}</div>`;}).join('')||'<p>没有可核验的事实声明；请结合拒答测试结果判断。</p>'}<h3>实际检索片段 · Recall@${state.run.top_k} ${pct(r.recall)}</h3>${(r.contexts||[]).map(c=>`<details class="claim"><summary class="mono">${esc(c.id)}</summary><p>${esc(c.text)}</p></details>`).join('')||'<p>未返回检索片段。</p>'}<div class="space-top"><button class="primary" data-action="select-trace" data-id="${esc(r.trace_id)}">${icon('trace')}审计完整链路</button></div>`);
}
function spanDetail(id){const span=state.spans.find(s=>s.span_id===id);if(!span)return;showDetail(`<h2>${esc(span.name)}</h2><div class="detail-meta"><span class="badge blue">${esc(span.kind)}</span><span class="badge ${span.status==='error'?'error':''}">${esc(span.status)}</span><span class="badge neutral">${ms(span.duration_ms)}</span></div><h3>身份与父链</h3><pre>${esc(JSON.stringify({trace_id:span.trace_id,span_id:span.span_id,parent_span_id:span.parent_span_id},null,2))}</pre>${span.error?`<div class="error-box">${esc(span.error)}</div>`:''}<h3>输入 / 工具入参</h3><pre>${esc(JSON.stringify(span.input,null,2))}</pre><h3>输出 / 工具结果</h3><pre>${esc(JSON.stringify(span.output,null,2))}</pre><h3>Prompt、用量与运行属性</h3><pre>${esc(JSON.stringify(span.attributes,null,2))}</pre>`);}
function settings(){showDetail(`<h2>本地模型与 Agent 配置</h2><p>在项目根目录将 .env.example 复制为 .env，填入配置后重启服务。密钥只由本地后端读取。</p><div class="detail-meta"><span class="badge ${state.config.model_configured?'':'warn'}">裁判：${state.config.model_configured?'已配置':'未配置'}</span><span class="badge ${state.config.agents_configured?'':'warn'}">两个 Agent：${state.config.agents_configured?'已配置':'未配置'}</span></div><h3>裁判模型</h3><pre>EVALFORGE_API_BASE=https://your-provider.example/v1\nEVALFORGE_API_KEY=your-local-secret\nEVALFORGE_MODEL=your-model-id\n# 可选：每百万 token 美元价格\nEVALFORGE_INPUT_PRICE=\nEVALFORGE_OUTPUT_PRICE=</pre><h3>两个待测版本</h3><pre>EVALFORGE_AGENT_1_URL=http://127.0.0.1:9001/answer\nEVALFORGE_AGENT_1_NAME=LogiGraph v1.0\nEVALFORGE_AGENT_2_URL=http://127.0.0.1:9002/answer\nEVALFORGE_AGENT_2_NAME=LogiGraph v2.0</pre><p>Agent 接收 question、top_k、document_id，返回 answer、contexts，以及可选顶层 prompt_tokens、completion_tokens、cost_usd 字段。完整协议见项目 README 和 API 文档。未配置时可继续使用离线演示。</p>`);}
async function upload(file){
  if(!file)return;if(file.size>8*1024*1024)throw new Error('文档不能超过 8 MB');
  state.busy=true;render();try{await api('/documents?name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});await refresh();toast('文档已导入，可以生成候选测试集');}finally{state.busy=false;render();}
}
const actions={
  settings,
  upload:()=>$('#file-input').click(),
  async generate(){
    const documentId=$('#document-select').value,count=Number($('#case-count').value),mode=$('#generation-mode').value;
    if(!documentId)throw new Error('请先导入文档');if(!Number.isInteger(count)||count<1||count>50)throw new Error('题目数量应为 1 至 50');
    state.busy=true;render();try{state.dataset=await post('/datasets',{document_id:documentId,count,mode});await refresh();toast(`已生成 ${state.dataset.cases.length} 条候选题，请审阅后确认`);}finally{state.busy=false;render();}
  },
  async 'view-dataset'(el){state.dataset=await api('/datasets/'+el.dataset.id);render();},
  'golden-detail':el=>goldenDetail(el.dataset.id),
  async approve(el){state.dataset=await post('/datasets/'+el.dataset.id+'/approve',{});await refresh();render();toast('测试集已确认，可以用于回归');},
  async 'start-run'(){
    const datasetId=$('#dataset-select').value,mode=$('#run-mode').value,k=Number($('#top-k').value),name=$('#run-name').value.trim();
    if(!datasetId)throw new Error('请先确认一份测试集');if(!Number.isInteger(k)||k<1||k>20)throw new Error('top-k 应为 1 至 20');if(!name)throw new Error('请输入运行名称');
    state.busy=true;render();try{const run=await post('/runs',{dataset_id:datasetId,mode,top_k:k,name});state.run=await api('/runs/'+run.id);await refresh();state.filter='all';toast('评测已开始，结果会自动更新');}finally{state.busy=false;render();}
  },
  async 'select-run'(el){state.run=await api('/runs/'+el.dataset.id);state.filter='all';if(state.page!=='runs'){location.hash='runs';}else render();},
  filter(el){state.filter=el.dataset.id;render();},
  'result-detail':el=>resultDetail(el.dataset.id,el.dataset.version),
  async 'select-trace'(el){state.traceId=el.dataset.id;$('#detail').close();await loadTraces();if(state.page!=='traces')location.hash='traces';else render();},
  'span-detail':el=>spanDetail(el.dataset.id),
  async 'search-trace'(){state.traceId=$('#trace-search').value.trim();if(state.traceId&&!/^[a-f0-9]{32}$/.test(state.traceId))throw new Error('请输入完整的 32 位 Trace ID');await loadTraces();render();},
  async 'all-traces'(){state.traceId='';await loadTraces();render();},
  async 'refresh-traces'(){await loadTraces();render();toast('链路已刷新');}
};
document.addEventListener('click',event=>{if(event.target.closest('.close-dialog')){$('#detail').close();return;}const el=event.target.closest('[data-action]');if(el&&!el.disabled){Promise.resolve().then(()=>actions[el.dataset.action]?.(el)).catch(error=>toast(error.message,true));}});
document.addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.matches('[role="button"],tr.clickable'))event.target.click();if(event.key==='Enter'&&event.target.id==='trace-search')actions['search-trace']().catch(e=>toast(e.message,true));});
document.addEventListener('change',event=>{const el=event.target;if(el.id==='file-input')upload(el.files[0]).catch(e=>toast(e.message,true));if(el.id==='run-select'){api('/runs/'+el.value).then(run=>{state.run=run;state.filter='all';render();}).catch(e=>toast(e.message,true));}});
document.addEventListener('dragover',event=>{if(event.target.closest('#drop-zone'))event.preventDefault();});
document.addEventListener('drop',event=>{if(event.target.closest('#drop-zone')){event.preventDefault();upload(event.dataTransfer.files[0]).catch(e=>toast(e.message,true));}});
async function route(){state.page=['overview','datasets','runs','traces'].includes(location.hash.slice(1))?location.hash.slice(1):'overview';try{await refresh();render();}catch(error){toast(error.message,true);}}
window.addEventListener('hashchange',route);
await route();
setInterval(async()=>{
  if(state.polling||!['queued','running'].includes(state.run?.status))return;
  state.polling=true;
  try{state.run=await api('/runs/'+state.run.id);if(!['queued','running'].includes(state.run.status)){await refresh();toast(state.run.status==='completed'?'评测已完成':'评测已停止，请查看运行状态',state.run.status!=='completed');}if(state.page==='runs'||state.page==='overview')render();}
  catch(error){toast(error.message,true);}finally{state.polling=false;}
},1200);

