"""Drop into the v17.4 repository's tests/ directory.

Run: python -m unittest discover -s tests -p test_protocol_invariants.py -v
These two invariant tests intentionally FAIL against the reviewed v17.4 code.
Native operations are mocked; no live agent or provider calls are made.
"""
import contextlib
import io
import json
from unittest.mock import patch

from support import Base, memo
from common import Rejected, encode
from role_spawn import spawn
import dispatchctl


class ProtocolInvariants(Base):
    def test_rejected_retry_does_not_overwrite_existing_owner_delivery(self):
        packet_ref = self.issue()
        self.launch(packet_ref)
        packet = self.g.files.get(packet_ref)
        delivery = self.g.files.delivery_path(packet['id'], create=True)
        original = b'OWNER_WORK_IN_PROGRESS_DO_NOT_REPLACE\n'
        delivery.write_bytes(original)

        with patch('role_spawn.create_task') as create_task, patch('role_spawn.start_worker') as start_worker:
            with self.assertRaisesRegex(Rejected, 'native-confirmed failed'):
                spawn(self.g, retry_packet=packet_ref, runtime_view=self.view(),
                      workspace_key='local/main', dry_run=False)
        create_task.assert_not_called()
        start_worker.assert_not_called()
        self.assertEqual(delivery.read_bytes(), original,
                         'A rejected retry must not reset an existing attempt delivery.')

    def test_batch_ack_requires_release_of_every_one_shot_reviewer(self):
        messages = []
        reviewer_ids = []
        for wp_id in ('WP1', 'WP3'):
            candidate = self.candidate(wp_id)
            self.g.r0(candidate)
            packet_ref = self.issue('review_r1', wp_id)
            binding_ref = self.launch(packet_ref)
            binding = self.g.files.get(binding_ref)
            packet = self.g.files.get(packet_ref)
            review = {
                'schema_version': 9, 'outcome': 'pass',
                'target_digest': candidate['sha256'], 'summary': 'Local pass',
                'findings': [], 'source_memo': memo(),
            }
            self.g.files.delivery_path(packet['id'], create=True).write_bytes(encode(review))
            native = binding['receipt']
            reviewer_ids.append(native['dispatch_id'])
            messages.append({
                'type': 'worker_done', 'delivery_contract': 'current_delivery',
                'id': 'MSG-' + wp_id, 'run_id': 'RUN',
                'payload': json.dumps({
                    'taskId': native['task_id'], 'dispatchId': native['dispatch_id'],
                    'outcome': 'succeeded',
                }),
            })
        self.g.stage_worker_done_batch(messages, 'BATCH-MULTI-REVIEW')
        release_ids_at_ack = []
        with patch('dispatchctl.release_worker', return_value={'ok': True}) as release:
            def acknowledge(*args, **kwargs):
                release_ids_at_ack.append([call.args[1] for call in release.call_args_list])
                return {'ok': True}

            with patch('dispatchctl.acknowledge_events', side_effect=acknowledge) as ack:
                for dispatch_id in reviewer_ids:
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        status = dispatchctl.main(['--repo', str(self.repo), 'result', dispatch_id])
                    self.assertEqual(status, 0, stderr.getvalue())
                ack.assert_called_once()
        self.assertEqual(set(release_ids_at_ack[0]), set(reviewer_ids),
                         'Do not acknowledge/clear a batch while another one-shot release is pending.')
