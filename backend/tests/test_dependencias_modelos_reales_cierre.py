"""Real installed graph/model libraries, offline tiny synthetic weights."""
from types import SimpleNamespace
import math
import pytest

@pytest.fixture
def tiny_models(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    from transformers import BertConfig, BertTokenizerFast, BertModel, BertForSequenceClassification
    vocabulary = tmp_path / "vocab.txt"
    vocabulary.write_text("\n".join(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "synthetic", "text", "one", "two"]), encoding="utf-8")
    tokenizer = BertTokenizerFast(vocab_file=str(vocabulary))
    config = BertConfig(vocab_size=9, hidden_size=16, num_hidden_layers=1,
                        num_attention_heads=2, intermediate_size=32, num_labels=1)
    embedding = tmp_path / "embedding"
    reranker = tmp_path / "reranker"
    BertModel(config).save_pretrained(embedding, safe_serialization=True)
    tokenizer.save_pretrained(embedding)
    BertForSequenceClassification(config).save_pretrained(reranker, safe_serialization=True)
    tokenizer.save_pretrained(reranker)
    return embedding, reranker

def test_bge_wrapper_amb_flag_real_cpu_offline(tiny_models, monkeypatch):
    from app.rag import embeddings
    settings = SimpleNamespace(embedding_model=str(tiny_models[0]), embedding_dim=16, embedder_device="cpu")
    monkeypatch.setattr(embeddings, "get_settings", lambda: settings)
    vectors = embeddings.BGEEmbedder().embed(["synthetic text one", "synthetic text two"])
    assert len(vectors) == 2 and all(len(v) == 16 for v in vectors)
    assert all(math.isfinite(x) for v in vectors for x in v)

def test_reranker_wrapper_amb_flag_real_cpu_offline(tiny_models, monkeypatch):
    from app.rag import rerank
    settings = SimpleNamespace(reranker_model=str(tiny_models[1]), reranker_device="cpu")
    monkeypatch.setattr(rerank, "get_settings", lambda: settings)
    candidates = [rerank.CandidatRerank("synthetic text one", {"id": 1}),
                  rerank.CandidatRerank("synthetic text two", {"id": 2})]
    result = rerank.BGEReranker().rerank("synthetic text", candidates, 2)
    assert len(result) == 2 and all(math.isfinite(score) for _, score in result)

def test_sentence_transformers_real_amb_pesos_sintetics(tiny_models):
    from sentence_transformers import SentenceTransformer, models
    transformer = models.Transformer(str(tiny_models[0]), model_args={"local_files_only": True, "trust_remote_code": False})
    model = SentenceTransformer(modules=[transformer, models.Pooling(16)], device="cpu")
    vector = model.encode(["synthetic text one"], convert_to_numpy=True)
    assert vector.shape == (1, 16)

def test_langgraph_real_compila_i_invoca_sense_checkpoint():
    from typing import TypedDict
    from langgraph.graph import StateGraph, END
    class State(TypedDict):
        count: int
    graph = StateGraph(State)
    graph.add_node("increment", lambda state: {"count": state["count"] + 1})
    graph.set_entry_point("increment")
    graph.add_edge("increment", END)
    compiled = graph.compile()
    assert compiled.invoke({"count": 3})["count"] == 4
    assert compiled.checkpointer is None

