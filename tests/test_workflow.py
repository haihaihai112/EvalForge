import asyncio
import json
import io
import zipfile
import httpx
import pytest

from evalforge.documents import import_document
from evalforge.datasets import generate_dataset
from evalforge.providers import DemoJudge, ModelJudge
from evalforge.demo import SAMPLE_SOP


def test_document_chunks_and_fifty_demo_cases_have_real_sources():
    document = import_document("物流.md", SAMPLE_SOP.encode())
    assert len(document["chunks"]) >= 10
    dataset = asyncio.run(generate_dataset(DemoJudge(), document, 50))
    assert len(dataset["cases"]) == 50
    assert len({c["question"] for c in dataset["cases"]}) == 50
    valid_ids = {c["id"] for c in document["chunks"]}
    assert all(set(c["expected_chunk_ids"]) <= valid_ids for c in dataset["cases"])
    assert any(c["category"] == "multi_hop" for c in dataset["cases"])
    assert any(c["expected_refusal"] for c in dataset["cases"])
    assert dataset["mode"] == "demo"


def test_empty_or_unsupported_document_is_rejected():
    with pytest.raises(ValueError):
        import_document("empty.txt", b" ")
    with pytest.raises(ValueError):
        import_document("file.exe", b"MZ" + b"x" * 100)


def test_docx_extracts_original_text_for_evidence():
    text = "破损、污染或批次不明的货品必须移入隔离区。在质控放行前不得进入可售库存。"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    doc = import_document("sop.docx", buffer.getvalue())
    assert doc["chunks"][0]["text"] == text
    assert doc["text"][doc["chunks"][0]["start"]:doc["chunks"][0]["end"]] == text


def test_image_only_pdf_is_not_silently_accepted():
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ValueError, match="OCR"):
        import_document("scan.pdf", buffer.getvalue())


def test_real_model_json_contract_and_usage_are_checked():
    def handler(request):
        body = json.loads(request.content)
        assert body["messages"][0]["role"] == "system"
        assert body["response_format"] == {"type": "json_object"}
        assert request.headers["Authorization"] == "Bearer local-test"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"claims": []}'}}], "usage": {"prompt_tokens": 20, "completion_tokens": 10}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            judge = ModelJudge("https://model.test/v1", "local-test", "fixture-model", input_price=2, output_price=4, client=client)
            result = await judge.complete("claims", {"answer": "现有材料不足"})
            assert result == {"claims": []}
            assert judge.usage["cost_usd"] == pytest.approx(.00008)
    asyncio.run(run())


def test_invalid_model_json_does_not_succeed():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]}))) as client:
            judge = ModelJudge("https://model.test/v1", "key", "model", client=client)
            with pytest.raises(RuntimeError):
                await judge.complete("claims", {"answer": "x"})
    asyncio.run(run())


@pytest.mark.parametrize("body", [[], {"usage": [1]}, {"usage": {"prompt_tokens": -1, "completion_tokens": 2}}])
def test_malformed_provider_envelope_is_controlled_error(body):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))) as client:
            judge = ModelJudge("https://model.test/v1", "key", "model", client=client)
            with pytest.raises(RuntimeError, match="模型调用失败"):
                await judge.complete("claims", {"answer": "x"})
    asyncio.run(run())


def test_malformed_dataset_candidates_do_not_crash():
    class MalformedJudge:
        mode = "live"
        usage = {"cost_usd": None}

        async def complete(self, task, payload):
            return {"cases": [None, {"question": "x", "category": "factual", "expected_refusal": False, "expected_answer": "x", "evidence": [None]}]}

    document = import_document("sop.md", SAMPLE_SOP.encode())
    with pytest.raises(ValueError, match="有效题目"):
        asyncio.run(generate_dataset(MalformedJudge(), document, 5))
