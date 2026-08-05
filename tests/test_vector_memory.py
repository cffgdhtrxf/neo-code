import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import neo_code

pytestmark = pytest.mark.skipif(
    not neo_code._HAS_VECTOR_MEMORY,
    reason="chromadb / sentence-transformers 未安装（CI 等环境跳过）",
)


class MockCollection:
    def __init__(self):
        self._docs = {}
        self._embeddings = {}
        self._next_id = 0

    def add(self, embeddings, documents, ids):
        for e, d, i in zip(embeddings, documents, ids):
            self._docs[i] = d
            self._embeddings[i] = e
            self._next_id = max(self._next_id, int(i) + 1)

    def query(self, query_embeddings, n_results, include):
        docs = list(self._docs.values())[:n_results]
        return {
            "documents": [docs],
            "ids": [list(self._docs.keys())[:n_results]],
            "distances": [[0.1] * len(docs)],
        }

    def get(self):
        return {"ids": list(self._docs.keys()), "documents": list(self._docs.values())}


class MockClient:
    def delete_collection(self, name):
        pass

    def create_collection(self, name):
        return MockCollection()


class TestVectorMemory:
    @pytest.fixture
    def mock_chroma(self):
        with patch("chromadb.PersistentClient") as mock_persistent:
            client = MagicMock()
            collection = MockCollection()
            client.get_or_create_collection.return_value = collection
            client.delete_collection = MagicMock()
            client.create_collection.return_value = MockCollection()
            mock_persistent.return_value = client
            yield mock_persistent

    @pytest.fixture
    def mock_sentence_transformer(self):
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            model = MagicMock()
            model.encode.return_value = MagicMock()
            model.encode.return_value.tolist.return_value = [0.1] * 384
            mock_st.return_value = model
            yield mock_st

    def test_init_creates_collection(self, tmp_path, mock_chroma, mock_sentence_transformer):
        with patch.object(neo_code, '_HAS_VECTOR_MEMORY', True):
            from neo_code import VectorMemory
            vm = VectorMemory(tmp_path)
            assert vm.turn_count == 0

    def test_add_turn_increments_seq(self, tmp_path, mock_chroma, mock_sentence_transformer):
        with patch.object(neo_code, '_HAS_VECTOR_MEMORY', True):
            from neo_code import VectorMemory
            vm = VectorMemory(tmp_path)
            assert vm.turn_count == 0
            vm.add_turn("user msg", "assistant msg")
            assert vm.turn_count == 1
            vm.add_turn("user msg 2", "assistant msg 2")
            assert vm.turn_count == 2

    def test_query_returns_documents(self, tmp_path, mock_chroma, mock_sentence_transformer):
        with patch.object(neo_code, '_HAS_VECTOR_MEMORY', True):
            from neo_code import VectorMemory
            vm = VectorMemory(tmp_path)
            vm.add_turn("hello world", "hi there")
            results = vm.query("hello")
            assert len(results) == 1
            assert "hello world" in results[0]

    def test_clear_resets_collection(self, tmp_path, mock_chroma, mock_sentence_transformer):
        with patch.object(neo_code, '_HAS_VECTOR_MEMORY', True):
            from neo_code import VectorMemory
            vm = VectorMemory(tmp_path)
            vm.add_turn("q1", "a1")
            assert vm.turn_count == 1
            vm.clear()
            assert vm.turn_count == 0

    def test_storage_size_mb(self, tmp_path, mock_chroma, mock_sentence_transformer):
        with patch.object(neo_code, '_HAS_VECTOR_MEMORY', True):
            from neo_code import VectorMemory
            vm = VectorMemory(tmp_path)
            size = vm.storage_size_mb
            assert isinstance(size, float)
            assert size >= 0.0

    def test_migrate_from_history(self, tmp_path, mock_chroma, mock_sentence_transformer):
        history = tmp_path / "history.json"
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "question 1"},
            {"role": "assistant", "content": "answer 1"},
            {"role": "user", "content": "question 2"},
            {"role": "assistant", "content": "answer 2"},
        ]
        history.write_text(json.dumps({"messages": messages}), encoding="utf-8")

        with patch.object(neo_code, '_HAS_VECTOR_MEMORY', True):
            from neo_code import VectorMemory
            vm = VectorMemory.migrate_from_history(tmp_path, history)
            assert vm is not None
            assert vm.turn_count == 2
            assert not history.exists()
            migrated = history.with_suffix(".json.migrated")
            assert migrated.exists()

    def test_migrate_from_missing_history(self, tmp_path, mock_chroma, mock_sentence_transformer):
        with patch.object(neo_code, '_HAS_VECTOR_MEMORY', True):
            from neo_code import VectorMemory
            result = VectorMemory.migrate_from_history(tmp_path, tmp_path / "nonexistent.json")
            assert result is None

    def test_migrate_without_vector_memory(self, tmp_path):
        history = tmp_path / "history.json"
        history.write_text(json.dumps([{"role": "user", "content": "q"}]))
        with patch.object(neo_code, '_HAS_VECTOR_MEMORY', False):
            from neo_code import VectorMemory
            result = VectorMemory.migrate_from_history(tmp_path, history)
            assert result is None
