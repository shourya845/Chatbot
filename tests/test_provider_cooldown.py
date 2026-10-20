import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from langchain_core.messages import AIMessage, AIMessageChunk

import agent


class RateLimitError(Exception):
    status_code = 429

    def __init__(self, retry_after='30'):
        self.response = SimpleNamespace(status_code=429, headers={'retry-after': retry_after})


class CooldownTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        state = patch.object(agent, 'groq_retry_at', 0.0)
        state.start()
        self.addCleanup(state.stop)
        environment = patch.dict('os.environ', {'GROQ_API_KEY': 'test-not-real'})
        environment.start()
        self.addCleanup(environment.stop)

    async def test_call_cooldown_skips_groq_until_retry_after_expires(self):
        primary = Mock()
        primary.bind_tools.return_value = primary
        primary.ainvoke = AsyncMock(side_effect=[RateLimitError(), AIMessage(content='Cloud answer')])
        local = Mock()
        local.bind_tools.return_value = local
        local.ainvoke = AsyncMock(return_value=AIMessage(content='Local answer'))
        with patch('agent.provider_model', side_effect=lambda p: primary if p == 'groq' else local), \
                patch('agent.monotonic', return_value=100) as clock:
            self.assertEqual((await agent.call_llm([]))['content'], 'Local answer')
            self.assertEqual((await agent.call_llm([], allow_tools=False))['content'], 'Local answer')
            primary.ainvoke.assert_awaited_once()
            clock.return_value = 131
            self.assertEqual((await agent.call_llm([]))['content'], 'Cloud answer')
            self.assertEqual(primary.ainvoke.await_count, 2)

    async def test_stream_rate_limit_also_sets_the_shared_cooldown(self):
        async def failed(messages):
            raise RateLimitError('12.5')
            yield
        async def local_stream(messages):
            yield AIMessageChunk(content='Local answer')
        primary = SimpleNamespace(astream=failed)
        local = SimpleNamespace(astream=local_stream)
        with patch('agent.model_candidates', return_value=iter([('groq', primary), ('ollama', local)])), \
                patch('agent.monotonic', return_value=100):
            self.assertEqual([part async for part in agent.model_tokens([])], ['Local answer'])
        self.assertEqual(agent.groq_retry_at, 112.5)

    def test_invalid_retry_headers_use_a_safe_default(self):
        for header in (None, 'invalid', 'nan', 'inf', '-1', '0'):
            with self.subTest(header=header), patch('agent.monotonic', return_value=100):
                agent.groq_retry_at = 0
                agent.cool_down_groq(RateLimitError(header))
                self.assertEqual(agent.groq_retry_at, 160)

    def test_unrelated_errors_do_not_disable_groq(self):
        agent.cool_down_groq(RuntimeError('Network interrupted'))
        self.assertEqual(agent.groq_retry_at, 0)
