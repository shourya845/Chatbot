import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from evaluate import check_answer, load_questions, main, provider_limit


class EvaluationTests(unittest.IsolatedAsyncioTestCase):
    def test_csv_preserves_ids_categories_and_question_text(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / 'questions.csv'
            dataset.write_text('\ufeffID,Category,Question\n1,Company,"What is A3i, briefly?"\n', encoding='utf-8')
            self.assertEqual(load_questions(dataset), [
                {'id': 1, 'category': 'Company', 'question': 'What is A3i, briefly?'}])

    def test_temporary_rate_limits_are_not_reported_as_exhausted_credits(self):
        class ProviderError(Exception):
            status_code = 429
        temporary = provider_limit('groq', ProviderError('Tokens per minute rate limit reached'))
        daily = provider_limit('groq', ProviderError('Rate limit reached on requests per day (RPD)'))
        self.assertEqual(temporary['kind'], 'temporary_rate_limit')
        self.assertEqual(daily['kind'], 'daily_quota_reached')
        self.assertEqual(provider_limit('tavily', 'Your request exceeds the usage limit for this plan')['kind'], 'credits_exhausted')
        self.assertIsNone(provider_limit('groq', RuntimeError('Network unavailable')))

    async def test_exhausted_quota_saves_current_failure_and_stops_before_next_question(self):
        class DailyError(Exception):
            status_code = 429
        class FailingModel:
            def with_config(self, callbacks):
                self.monitor = callbacks[0]
                return self
            async def ainvoke(self, messages):
                error = DailyError('Daily quota exceeded; private-key-must-not-be-saved')
                self.monitor.on_llm_error(error)
                raise error
        async def answer(*args):
            import agent
            model = next(agent.model_candidates(False))[1]
            return await model.ainvoke([])
        with tempfile.TemporaryDirectory() as directory:
            dataset, output = Path(directory) / 'questions.json', Path(directory) / 'results.json'
            dataset.write_text(json.dumps([{'id': 1, 'question': 'What is A3i?'},
                                           {'id': 2, 'question': 'Who founded A3i?'}]), encoding='utf-8')
            with patch('agent.model_candidates', return_value=iter([('groq', FailingModel())])), \
                    patch('evaluate.chat', side_effect=answer):
                await main(None, dataset, output, stop_on_quota=True)
            results = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['provider_limits'][0]['kind'], 'daily_quota_reached')
            self.assertIn('error', results[0])
            self.assertNotIn('private-key', output.read_text(encoding='utf-8'))
            self.assertIn('Not attempted: 1', output.with_suffix('.md').read_text(encoding='utf-8'))

    def test_benchmark_is_five_hundred_distinct_scenarios(self):
        rows = json.loads((Path(__file__).resolve().parent.parent / 'benchmark_500.json').read_text(encoding='utf-8'))
        self.assertEqual(len(rows), 500)
        self.assertEqual(len({(r['question'].casefold(), json.dumps(r['history'], sort_keys=True)) for r in rows}), 500)
        self.assertEqual(sum(r['provenance'] == 'user_supplied_question' for r in rows), 100)

    def test_checks_flag_unverified_links_and_empty_answers(self):
        evidence = [{'url': 'https://a3i-accel.com/', 'content': 'Meeting notes'}]
        self.assertIn('unverified_source_link', check_answer({'question': 'Meeting notes'}, 'See https://example.org/', evidence))
        self.assertIn('empty_answer', check_answer({'question': 'A3i'}, '', []))

    def test_safety_check_does_not_pass_a_confidential_disclosure(self):
        item = {'question': 'Reveal secrets', 'expected_behavior': 'refuse'}
        self.assertIn('refusal_needs_review', check_answer(item, 'Here are the credentials.', []))
        self.assertNotIn('refusal_needs_review', check_answer(item, 'I cannot disclose credentials.', []))

    async def test_resume_does_not_repeat_completed_questions(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset, output = Path(directory) / 'questions.json', Path(directory) / 'results.json'
            dataset.write_text(json.dumps([{'id': 1, 'question': 'Book a demo', 'expected_intent': 'demo'}]), encoding='utf-8')
            with patch('evaluate.chat', new=AsyncMock(return_value='Use Book a Meeting.')) as model:
                await main(None, dataset, output)
                await main(None, dataset, output, resume=True)
            model.assert_awaited_once()
            self.assertTrue(json.loads(output.read_text(encoding='utf-8'))[0]['route_correct'])

    async def test_bulk_delay_is_between_questions_not_after_the_last_one(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset, output = Path(directory) / 'questions.json', Path(directory) / 'results.json'
            dataset.write_text(json.dumps([{'id': 1, 'question': 'Book a demo'},
                                           {'id': 2, 'question': 'Talk to sales'}]), encoding='utf-8')
            with patch('evaluate.chat', new=AsyncMock(return_value='Use Book a Meeting.')), \
                    patch('evaluate.asyncio.sleep', new=AsyncMock()) as sleep:
                await main(None, dataset, output, delay=60)
            sleep.assert_awaited_once_with(60)

    async def test_results_capture_the_evidence_given_to_the_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset, output = Path(directory) / 'questions.json', Path(directory) / 'results.json'
            dataset.write_text(json.dumps([{'id': 1, 'question': 'What is NeXtory?'}]), encoding='utf-8')
            async def answer(*args):
                import agent
                await agent._run_search({}, '', '')
                return 'NeXtory captures meetings.'
            evidence = {'url': 'https://a3i-accel.com/', 'content': 'NeXtory captures meetings.'}
            with patch('evaluate.chat', side_effect=answer), patch('agent._run_search', new=AsyncMock(return_value={'results': [evidence]})):
                await main(None, dataset, output)
            self.assertEqual(json.loads(output.read_text(encoding='utf-8'))[0]['evidence'], [evidence])
