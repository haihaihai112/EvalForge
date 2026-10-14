"""Fictional SOP and deliberately fallible fixtures. No production logistics claim."""

SAMPLE_SOP = """# 北辰物流仓配作业规范（虚构演示资料）

入库预约：供应商须在到仓前 24 小时提交预约单。预约单应包含采购单号、货品清单、箱数与预计到仓时间。

到仓核验：收货员必须核对预约单与送货单。未预约车辆需经当班主管书面批准后进入卸货区。

收货验收：卸货后须核对 SKU、批次、数量与包装完整性。发现少货或破损必须拍照并创建异常单。

隔离要求：破损、污染或批次不明的货品必须移入隔离区。在质控放行前不得进入可售库存。

上架要求：验收通过后 4 小时内完成上架。系统库存以扫码上架完成时间为准，严禁先记账后上架。

温控要求：冷藏品储存温度为 2 至 8 摄氏度。温度每 30 分钟记录一次；超限须立即报警并隔离相关批次。

库存轮转：有有效期的商品按先到期先出执行。无有效期的商品按先进先出执行。

拣货复核：拣货员按系统任务扫码拣选，复核员须再次核对 SKU 和数量。拣货员不得复核自己的订单。

截单要求：当日 16:00 前审核通过的订单安排当日出库；之后的订单安排下一工作日出库。法定节假日以专项通知为准。

出库交接：装车前扫描包裹与运单并核对件数。承运商签署交接清单后，仓库方可将订单状态更新为已交接。

异常处理：客服接到丢件或破损反馈后 2 小时内建立工单。仓库在收到工单后 24 小时内提供拣货、复核与交接记录。

退货处理：退货入仓后先登记原订单、退货原因与外观情况。经质检确认可售后才能重新上架，不可售商品进入隔离区。

盘点管理：高价值货品每天盘点一次，普通货品每周盘点一次。盘点差异须由主管复核后再调整系统库存。

权限要求：库存调整和异常放行需要主管审批。审批记录至少保留 180 天，禁止共享个人系统账号。

数据边界：本制度不规定赔付金额、员工私人联系方式或车辆实时位置。缺少规则时应记录问题并请求制度负责人确认。
"""


def demo_cases(document, count):
    chunks = document["chunks"]
    candidates = []
    for i, chunk in enumerate(chunks):
        title = chunk["text"].split("：")[0].split(":")[0][:30]
        next_chunk = chunks[(i + 1) % len(chunks)]
        neighbor = next_chunk["text"].split("：")[0][:30]
        variants = [
            ("factual", f"关于{title}，SOP 的具体要求是什么？", [chunk], chunk["text"], False),
            ("scenario", f"新员工负责{title}，应执行哪些步骤和限制？", [chunk], chunk["text"], False),
            ("false_premise", f"有人说{title}的要求可以全部跳过，这符合制度吗？", [chunk], chunk["text"], False),
            ("multi_hop", f"同时处理{title}与{neighbor}时，需要满足哪些规定？", [chunk, next_chunk], chunk["text"] + "\n" + next_chunk["text"], False),
            ("unanswerable", f"负责{title}的员工私人手机号码是多少？", [], "现有 SOP 未提供该信息，应向制度负责人核实。", True),
        ]
        for category, question, evidence, expected, refusal in variants:
            candidates.append({"id": f"case_{len(candidates)+1:03}", "question": question, "category": category,
                               "expected_answer": expected, "expected_refusal": refusal,
                               "expected_chunk_ids": [c["id"] for c in evidence],
                               "evidence": [{"chunk_id": c["id"], "quote": c["text"]} for c in evidence],
                               "review_status": "candidate"})
    if count > len(candidates):
        raise ValueError(f"演示模板基于当前条款最多生成 {len(candidates)} 题，请降低数量或使用真实模型")
    # Interleave categories and clauses deterministically; never claim this is an LLM golden set.
    return candidates[:count]
