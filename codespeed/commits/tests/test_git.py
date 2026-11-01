from datetime import datetime
from django.test import TestCase, override_settings
from unittest.mock import Mock, patch

from codespeed import commits
from codespeed.commits.git import Git, getlogs
from codespeed.commits.logs import FunctionBackend, get_scm
from codespeed.models import Project, Revision, Branch, Environment


@override_settings(ALLOW_ANONYMOUS_POST=True)
class GitTest(TestCase):
    def setUp(self):
        self.env = Environment.objects.create(name='env')
        self.project = Project.objects.create(name='project',
                                              repo_path='path',
                                              repo_type=Project.GIT)
        self.branch = Branch.objects.create(name='default',
                                            project_id=self.project.id)
        self.revision = Revision.objects.create(
            **{
               'commitid': 'id1',
               'date': datetime.now(),
               'project_id': self.project.id,
               'branch_id': self.branch.id,
            }
        )

    @patch("codespeed.commits.git.Popen")
    def test_git_output_parsing(self, popen):
        # given
        outputs = {
            "log": b"id\x00long_id\x001583489681\x00author\x00email\x00msg\x00\x1e",
            "tag": b'tag',
        }

        def side_effect(cmd, *args, **kwargs):
            ret = Mock()
            ret.returncode = 0
            git_command = cmd[1] if len(cmd) > 0 else None
            output = outputs.get(git_command, b'')
            ret.communicate.return_value = (output, b'')
            return ret

        popen.side_effect = side_effect

        # when
        # revision doesn't matter here, git commands are mocked
        logs = getlogs(self.revision, self.revision)

        # then
        expected = {
            'date': '2020-03-06 04:14:41',
            'message': 'msg',
            'commitid': 'long_id',
            'author': 'author',
            'author_email': 'email',
            'body': '',
            'short_commit_id': 'id',
            'tag': 'tag',
        }
        self.assertEqual([expected], logs)

    @patch("codespeed.commits.git.Popen")
    def test_logs_through_dispatcher(self, popen):
        """commits.get_logs must reach the git backend for a Git project."""
        ret = Mock()
        ret.returncode = 0
        ret.communicate.return_value = (
            b"id\x00long_id\x001583489681\x00author\x00email\x00msg\x00\x1e", b'')
        popen.return_value = ret

        logs = commits.get_logs(self.revision, self.revision)

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]['commitid'], 'long_id')

    @patch("codespeed.commits.git.Popen")
    def test_get_commit_date(self, popen):
        ret = Mock()
        ret.returncode = 0
        ret.communicate.return_value = (b"1583489681\n", b'')
        popen.return_value = ret

        date = commits.get_commit_date(self.project, 'long_id')

        self.assertEqual(date, datetime(2020, 3, 6, 10, 14, 41))
        cmd = popen.call_args_list[-1][0][0]
        self.assertEqual(cmd[:3], ['git', 'log', '-1'])
        self.assertEqual(cmd[-1], 'long_id')

    @patch("codespeed.commits.git.Popen")
    def test_get_commit_date_unknown_commit_falls_back(self, popen):
        ret = Mock()
        ret.returncode = 128
        ret.communicate.return_value = (b'', b'fatal: bad object')
        popen.return_value = ret

        date = commits.get_commit_date(self.project, 'nope')

        # Unknown commit: today rather than an exception, as before
        self.assertEqual(date.date(), datetime.today().date())


class GetScmTest(TestCase):
    def make(self, repo_type, path='https://github.com/python/cpython'):
        return Project.objects.create(name='p-%s' % repo_type, repo_path=path,
                                      repo_type=repo_type)

    def test_git(self):
        self.assertIsInstance(get_scm(self.make(Project.GIT)), Git)

    def test_github_and_subversion_get_an_adapter(self):
        for repo_type in (Project.GITHUB, Project.SUBVERSION):
            self.assertIsInstance(get_scm(self.make(repo_type)), FunctionBackend)

    def test_subversion_has_no_commit_date(self):
        self.assertIsNone(get_scm(self.make(Project.SUBVERSION)).get_commit_date('1'))

    @patch("codespeed.commits.github.fetch_json")
    def test_github_commit_date_from_api(self, fetch_json):
        def fake(url):
            if url.endswith('/git/refs/tags'):
                return []
            return {'sha': 'abc', 'parents': [], 'message': 'm',
                    'committer': {'date': '2020-03-06T10:14:41Z'},
                    'author': {'name': 'a', 'email': 'a@example.com'}}
        fetch_json.side_effect = fake
        date = commits.get_commit_date(self.make(Project.GITHUB), 'abc')
        self.assertEqual(date.isoformat(), '2020-03-06T10:14:41+00:00')
        self.assertIn('/repos/python/cpython/git/commits/abc',
                      fetch_json.call_args_list[0][0][0])

    def test_no_logs(self):
        self.assertIsNone(get_scm(self.make(Project.NO_LOGS)))
        self.assertEqual(commits.get_logs.__name__, 'get_logs')
