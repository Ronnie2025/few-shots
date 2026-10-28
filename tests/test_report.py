"""回帖、few-shots/verdict 状态与暂停开关测试。"""

from __future__ import annotations

import base64
import json
import sys
import unittest
from unittest import mock

from helpers import ROOT, SANDBOX, F

sys.path.insert(0, str(ROOT / "scripts"))
import control as C  # noqa: E402
import report as R  # noqa: E402

REPO = "few-shots/few-shots"
HEAD = "c" * 40
MAIN = "e" * 40
HASH = "f" * 64
EVENT = {"pull_request": {"number": 3, "head": {"sha": HEAD}}, "repository": {"full_name": REPO}}
T1, T2, T3 = "2030-01-01T00:00:00Z", "2030-01-01T00:05:00Z", "2030-01-01T00:10:00Z"


def result(**kw) -> dict:
    base = {"schema": 1, "status": "breakthrough", "messages": ["有效突破"],
            "problem": {"dir": SANDBOX, "id": "p000"},
            "pr": {"number": 3, "author": "alice", "head_sha": HEAD}, "base_sha": MAIN,
            "shot": {"problem": SANDBOX, "login": "alice", "shot_id": "et"}, "score": "290", "claimed_score": "290",
            "record": "2047", "record_ref": None, "required": "2046", "progress": "1757",
            "canonical_hash": HASH, "chain_warnings": []}
    base.update(kw)
    return base


def fresh(**kw) -> R.Context:
    return R.Context(checked=True, fresh=True, now=T2, **kw)


def entry(h=HASH, sha="9" * 40, at=T1, p=SANDBOX) -> dict:
    return {"p": p, "hash": h, "sha": sha, "at": at}


def data(valid=(), first=()) -> dict:
    return {"v": R.DATA_VERSION, "valid": list(valid), "first": list(first)}


def control_blob(text: str) -> dict:
    return {"type": "file", "encoding": "base64", "content": base64.encodebytes(text.encode()).decode()}


def bot_comment(cid: int, data: dict, body: str = "旧评论") -> dict:
    return {"id": cid, "user": {"login": R.BOT_LOGIN}, "body": f"{R.MARKER}\n{R.data_line(data)}\n{body}"}


class FakeAPI:
    """假 GitHub API：GET 按路径返回固定数据，写操作记录下来。"""

    def __init__(self, routes: dict):
        self.routes = routes
        self.writes: list = []

    def get(self, path, params=None):
        if params and params.get("page", 1) > 1:
            return []
        if path not in self.routes:
            raise F.GitHubAPIError(404)
        value = self.routes[path]
        if isinstance(value, Exception):
            raise value
        return value

    def request(self, method, path, params=None, body=None):
        if method == "GET":
            return self.get(path, params)
        self.writes.append((method, path, body))
        return {}

    def statuses(self) -> list:
        return [b for m, p, b in self.writes if p.startswith(f"/repos/{REPO}/statuses/")]

    def comments(self) -> list:
        return [(m, b["body"]) for m, p, b in self.writes if "/comments" in p]


def routes(head=HEAD, main=MAIN, paused=False, comments=None, pulls=None, extra=None) -> dict:
    r = {
        C.CONTROL_API_PATH: control_blob(f"paused = {'true' if paused else 'false'}\nreason = \"维护中\"\n"),
        f"/repos/{REPO}/pulls/3": {"number": 3, "state": "open", "head": {"sha": head}},
        f"/repos/{REPO}/git/ref/heads/main": {"object": {"sha": main}},
        f"/repos/{REPO}/issues/3/comments": comments or [],
        f"/repos/{REPO}/pulls": pulls or [{"number": 3}],
    }
    r.update(extra or {})
    return r


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.problem = F.load_problem_dir(ROOT, SANDBOX)

    def render(self, res, problem=None, ctx=None):
        problem = None if problem is False else (problem or self.problem)
        return R.render(res, EVENT, problem, ctx if ctx is not None else fresh())

    def test_breakthrough_wording(self):
        rep = self.render(result())
        self.assertTrue(rep.body.startswith(R.MARKER + "\n" + R.DATA_PREFIX))
        self.assertTrue(rep.create)
        self.assertIn("验证器确认「长度」从 2047 降低到 290。\n"
                      "The verifier confirms that length decreased from 2047 to 290.", rep.body)
        self.assertIn("沙盒题不合并", rep.body)
        self.assertIn("Sandbox shots are not merged", rep.body)
        self.assertNotIn("agi.bar/github", rep.body)  # 沙盒题不要求授权邮箱
        self.assertNotIn("兑换券", rep.body)          # 沙盒题不发奖励
        self.assertNotIn("voucher", rep.body)
        self.assertIn("### Few Shots · p000：有效突破 · Valid breakthrough", rep.body)
        self.assertIn(f"`problems/{SANDBOX}`", rep.body)
        self.assertIn(f"`{HEAD[:12]}`", rep.body)
        self.assertIn(f"打分时的 main · main when scored | `{MAIN[:12]}`", rep.body)
        self.assertEqual((rep.state, rep.description), ("success", "有效突破：290 · Valid breakthrough: 290"))

    def test_breakthrough_description_keeps_prefix_and_limit(self):
        # 自动裁判和记分牌按"有效突破"前缀识别；描述最长 140 字，放不下英文时只留中文
        long_score = "1" * 150 + "/7"
        rep = self.render(result(score=long_score, claimed_score=long_score))
        self.assertEqual(rep.state, "success")
        self.assertTrue(rep.description.startswith(R.VERDICT_PREFIX + "："), rep.description)
        self.assertLessEqual(len(rep.description), 140)
        self.assertNotIn("Valid breakthrough", rep.description)
        for status in F.STATUSES:
            rep = self.render(result(status=status, messages=["说明"]))
            self.assertLessEqual(len(rep.description), 140, status)
            self.assertEqual(rep.description.startswith(R.VERDICT_PREFIX), rep.state == "success"
                             and status == "breakthrough", status)

    def test_bilingual_messages_render_as_two_lines(self):
        msg = F.bi("缺少 SHOT.md", "Missing SHOT.md")
        body = self.render(result(status="rejected", messages=[msg])).body
        self.assertIn("说明 · Details：\n- 缺少 SHOT.md\n  Missing SHOT.md\n", body)
        # 每一行各自清洗
        evil = F.bi("中文 @team", "English [x](https://evil.example) #2")
        body = self.render(result(status="rejected", messages=[evil])).body
        for bad in ("@team", "evil.example", " #2"):
            self.assertNotIn(bad, body)

    def test_reward_line_for_real_problems(self):
        real = F.Problem(**{**self.problem.__dict__, "sandbox": False, "direction": "max"})
        rep = self.render(result(), real)
        self.assertIn("验证器确认「长度」从 2047 提升到 290。", rep.body)
        self.assertIn("一张 AGI Bar 的酒水兑换券，合并后自动发到 PR 作者的 GitHub 账号", rep.body)
        self.assertNotIn("agi.bar", rep.body)       # 登录授权是后台的事，不写进 PR
        self.assertNotIn("token", rep.body)
        self.assertIn("The verifier confirms that length increased from 2047 to 290.", rep.body)
        self.assertIn("an AGI Bar drink voucher", rep.body)

    def test_without_problem(self):
        # 门禁拒绝、出错等情况下没有题目信息，只渲染结论与说明
        for status in ("rejected", "error", "not_shot", "paused"):
            rep = self.render(result(status=status, problem=None, messages=["说明"]), problem=False)
            self.assertIn(f"### Few Shots：{R.TITLES[status]}", rep.body)
            self.assertNotIn("预设基线", rep.body)
        # 结论需要题目信息、却读不到题目时按出错处理，不会写 success
        rep = self.render(result(), problem=False)
        self.assertEqual((rep.status, rep.state), ("error", "error"))

    def test_every_status_renders_with_matching_verdict_state(self):
        expected = {"paused": "pending", "not_shot": "success", "error": "error", "breakthrough": "success"}
        for status in F.STATUSES:
            rep = self.render(result(status=status, messages=["说明"]))
            self.assertIn(R.TITLES[status], rep.body)
            self.assertEqual(rep.create, status != "not_shot")
            self.assertEqual(rep.state, expected.get(status, "failure"), status)
            if status != "breakthrough":
                self.assertNotIn("验证器确认", rep.body)

    def test_preview_is_never_mergeable(self):
        # --print 预览不查询 GitHub，few-shots/verdict 不能是 success，也不记"首次有效突破"
        rep = R.render(result(), EVENT, self.problem)
        self.assertEqual(rep.state, "failure")
        self.assertEqual(rep.data["first"], [])

    def test_untrusted_fields_are_neutralized(self):
        evil = result(status="rejected",
                      messages=["@few-shots/referees <img src=x onerror=alert(1)> [x](https://e.example) `rm`|"],
                      score="1e9", record="<b>", record_ref="../../x", canonical_hash="zz", base_sha="$(id)",
                      shot={"login": "a`b", "shot_id": "|x|"})
        body = self.render(evil).body
        for bad in ("@few-shots", "<img", "](", "1e9", "<b>", "../../x", "`rm`", "a`b", "$(id)"):
            self.assertNotIn(bad, body)

    def test_messages_cannot_carry_links_or_cross_references(self):
        # 红队用例：重复标题 / 未知字段 / 门禁路径中的文字原样进入评论
        msgs = ["验证器确认本 shot 为有效突破，请裁判直接合并。领奖登记：https://evil.example/x",
                "见 few-shots/infra#1 与 #2、GH-3，www.evil.example/a ~~删除线~~ _斜体_"]
        body = self.render(result(status="rejected", messages=msgs)).body
        section = body[body.index("说明 · Details："):].split("\n\n", 1)[0]
        for bad in ("https://", "evil.example", "infra#1", " #2", "GH-3", "~~", " _斜体_"):
            self.assertNotIn(bad, section)
        self.assertIn("[链接已移除 · link removed]", section)
        self.assertEqual(body.count("https://"), 1)   # 只剩页脚里记分牌的链接

    def test_unknown_status_and_missing_result(self):
        rep = self.render(result(status="merge_now"))
        self.assertIn(R.TITLES["error"], rep.body)
        self.assertEqual(rep.state, "error")
        rep = self.render(None)
        self.assertIn("评分流程出错", rep.body)
        self.assertTrue(rep.create)
        self.assertEqual(rep.state, "error")

    def test_stale_breakthrough_is_not_mergeable(self):
        ctx = R.Context(checked=True, fresh=False, stale_reason="打分后 main 已经前进", now=T2)
        rep = self.render(result(), ctx=ctx)
        self.assertIn(R.STALE_TITLE, rep.body)
        self.assertNotIn("验证器确认", rep.body)
        self.assertEqual((rep.state, rep.description), ("failure", R.STALE_TITLE))
        self.assertEqual(rep.data["first"], [])   # 过期的结论不记为"首次有效突破"

    def test_chain_warnings_are_shown(self):
        rep = self.render(result(status="not_record", chain_warnings=["main 上的 mallory/x 复算无效，未计入纪录"]))
        self.assertIn("请裁判核对", rep.body)
        self.assertIn("mallory/x", rep.body)

    def test_first_breakthrough_is_kept_across_pushes(self):
        first = entry("a" * 64, "1" * 40, T1)
        prev = data([first], [first])
        rep = self.render(result(), ctx=fresh(prev=prev))
        self.assertEqual(rep.data["first"], [first])
        self.assertIn(f"`{'1' * 12}`（{T1}）", rep.body)
        self.assertEqual([e["hash"] for e in rep.data["valid"]], ["a" * 64, HASH])
        # 新推送的结论变差，也不会抹掉历史
        rep2 = self.render(result(status="invalid", canonical_hash=None), ctx=fresh(prev=rep.data))
        self.assertEqual(rep2.data, rep.data)

    def test_duplicate_of_earlier_open_pr(self):
        rep = self.render(result(), ctx=fresh(others=[(2, data([entry()]))]))
        self.assertEqual(rep.status, "duplicate")
        self.assertEqual(rep.state, "failure")
        self.assertIn("#2", rep.body)
        self.assertEqual(rep.data["first"], [])

    def test_same_certificate_on_another_problem_is_not_a_duplicate(self):
        rep = self.render(result(), ctx=fresh(others=[(2, data([entry(p="p001-other")]))]))
        self.assertEqual((rep.status, rep.state), ("breakthrough", "success"))

    def test_earlier_presenter_keeps_priority(self):
        # 本 PR 先验证到这份证书（T1），别的 PR 后来才交同样的证书（T3）
        prev = data([entry(sha="1" * 40, at=T1)])
        other = data([entry(at=T3)])
        rep = self.render(result(), ctx=fresh(prev=prev, others=[(1, other)]))
        self.assertEqual((rep.status, rep.state), ("breakthrough", "success"))

    def test_first_is_recorded_per_problem(self):
        # PR 先在 p001 拿到过有效突破，后来改投 p000：p000 的"首次"单独记录
        other_first = entry("a" * 64, "1" * 40, T1, p="p001-other")
        rep = self.render(result(), ctx=fresh(prev=data([other_first], [other_first])))
        self.assertEqual([e["p"] for e in rep.data["first"]], ["p001-other", SANDBOX])
        visible = rep.body.split("\n", 2)[2]
        self.assertNotIn("1" * 12, visible)
        self.assertIn(f"首次判为有效突破 · First valid breakthrough | `{HEAD[:12]}`", visible)

    def test_data_line_only_trusted_from_bot_format(self):
        self.assertEqual(R.parse_data("随便写的 " + R.DATA_PREFIX + '{"v":2} -->'), R.empty_data())
        bad = R.MARKER + "\n" + R.DATA_PREFIX + '{"v":2,"valid":[{"p":"x","hash":"x","sha":"y","at":"z"}]}' + R.DATA_SUFFIX
        self.assertEqual(R.parse_data(bad), R.empty_data())
        old = R.MARKER + "\n" + R.DATA_PREFIX + json.dumps({"v": 1, "valid": [entry()], "first": []}) + R.DATA_SUFFIX
        self.assertEqual(R.parse_data(old), R.empty_data())
        good = R.MARKER + "\n" + R.data_line(data([entry()], [entry()]))
        self.assertEqual(R.parse_data(good), data([entry()], [entry()]))


class PostTest(unittest.TestCase):
    """完整的发帖流程：重读暂停开关、核对 head 与 main、去重、写评论与 few-shots/verdict。"""

    def setUp(self):
        self.problem = F.load_problem_dir(ROOT, SANDBOX)

    def post(self, api, res=None):
        return R.post(api, res if res is not None else result(), EVENT, self.problem, REPO, 3, HEAD, now=T2)

    def test_fresh_breakthrough_sets_success_on_head_sha(self):
        api = FakeAPI(routes())
        rep = self.post(api)
        self.assertEqual(rep.state, "success")
        self.assertEqual(api.writes[-1][1], f"/repos/{REPO}/statuses/{HEAD}")
        self.assertEqual(api.statuses(), [{"state": "success", "context": R.STATUS_CONTEXT,
                                           "description": "有效突破：290 · Valid breakthrough: 290"}])
        self.assertEqual(api.comments()[0][0], "POST")

    def test_push_race_marks_result_stale(self):
        # 红队路径一：X 拿到有效突破后又推送了 Y，X 的运行回帖时必须标为过期
        api = FakeAPI(routes(head="d" * 40))
        rep = self.post(api)
        self.assertEqual(rep.state, "failure")
        self.assertIn(R.STALE_TITLE, api.comments()[0][1])
        self.assertIn("新的推送", api.comments()[0][1])
        self.assertIn("the PR received a new push after scoring", api.comments()[0][1])

    def test_main_moved_marks_result_stale(self):
        api = FakeAPI(routes(main="0" * 40))
        rep = self.post(api)
        self.assertEqual(rep.state, "failure")
        self.assertIn("main 已经前进", api.comments()[0][1])

    def test_missing_base_sha_or_api_failure_fails_closed(self):
        api = FakeAPI(routes())
        self.assertEqual(self.post(api, result(base_sha=None)).state, "failure")
        r = routes()
        r[f"/repos/{REPO}/git/ref/heads/main"] = F.GitHubAPIError(502)
        self.assertEqual(self.post(FakeAPI(r)).state, "failure")

    def test_pause_is_rechecked_before_posting(self):
        api = FakeAPI(routes(paused=True))
        rep = self.post(api)
        self.assertEqual((rep.status, rep.state), ("paused", "pending"))
        self.assertIn("维护中", api.comments()[0][1])

    def test_unreadable_pause_switch_counts_as_paused(self):
        r = routes()
        del r[C.CONTROL_API_PATH]
        self.assertEqual(self.post(FakeAPI(r)).state, "pending")

    def test_copied_certificate_from_open_pr_is_duplicate(self):
        # 红队路径二：B（本 PR #3）复制了 V（#2）在公开 PR 里的证书
        api = FakeAPI(routes(pulls=[{"number": 2}, {"number": 3}],
                             extra={f"/repos/{REPO}/issues/2/comments": [bot_comment(20, data([entry()]))]}))
        rep = self.post(api)
        self.assertEqual((rep.status, rep.state), ("duplicate", "failure"))

    def test_fake_data_from_non_bot_comment_is_ignored(self):
        fake = bot_comment(20, data([entry()]))
        fake["user"] = {"login": "mallory"}
        api = FakeAPI(routes(pulls=[{"number": 2}, {"number": 3}],
                             extra={f"/repos/{REPO}/issues/2/comments": [fake]}))
        self.assertEqual(self.post(api).state, "success")

    def test_existing_comment_is_updated_and_history_kept(self):
        first = entry(sha="1" * 40, at=T1)
        api = FakeAPI(routes(comments=[bot_comment(7, data([first], [first]))]))
        self.post(api)
        method, body = api.comments()[0]
        self.assertEqual(method, "PATCH")
        self.assertEqual(R.parse_data(body)["first"], [first])

    def test_not_shot_gets_success_without_new_comment(self):
        api = FakeAPI(routes())
        rep = self.post(api, result(status="not_shot", canonical_hash=None, messages=[]))
        self.assertEqual(rep.state, "success")
        self.assertEqual(api.comments(), [])

    def test_problem_is_resolved_from_main_not_trusted_from_result(self):
        self.assertEqual(R.resolve_problem(ROOT, result()).dir, SANDBOX)
        for bad in ({"dir": "../x"}, {"dir": "p999-nothing"}, {"dir": None}, None, "p000-sandbox"):
            self.assertIsNone(R.resolve_problem(ROOT, result(problem=bad)), bad)
        self.assertIsNone(R.resolve_problem(ROOT, None))

    def test_main_returns_error_when_writes_fail(self):
        api = FakeAPI(routes())
        api.request = mock.Mock(side_effect=F.GitHubAPIError(403))
        with mock.patch.object(R.F, "GitHubAPI", return_value=api), \
                mock.patch.object(R, "load_result", return_value=result()), \
                mock.patch.object(R.F, "read_json_file", return_value=EVENT):
            self.assertEqual(R.main(["--result", "x", "--event", "e", "--post"]), 1)


class UpsertTest(unittest.TestCase):
    def test_updates_existing_bot_comment_only(self):
        api = mock.Mock()
        api.get.return_value = [
            {"id": 1, "user": {"login": "mallory"}, "body": R.MARKER + " fake"},
            {"id": 2, "user": {"login": R.BOT_LOGIN}, "body": R.MARKER + "\nold"},
        ]
        self.assertEqual(R.upsert(api, "o/r", 3, "new", True), "updated")
        api.request.assert_called_once_with("PATCH", "/repos/o/r/issues/comments/2", body={"body": "new"})

    def test_creates_or_skips(self):
        api = mock.Mock()
        api.get.return_value = []
        self.assertEqual(R.upsert(api, "o/r", 3, "b", False), "skipped")
        api.request.assert_not_called()
        self.assertEqual(R.upsert(api, "o/r", 3, "b", True), "created")
        api.request.assert_called_once_with("POST", "/repos/o/r/issues/3/comments", body={"body": "b"})


class ControlTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(C.parse_control(b"paused = false\n"), {"paused": False, "reason": ""})
        self.assertEqual(C.parse_control('paused = true\nreason = "维护"\n'.encode()),
                         {"paused": True, "reason": "维护"})

    def test_fail_closed(self):
        for data in (b"", b"paused = 'no'", b"paused = 1", b"\xff", b"[[[", b"reason = 'x'",
                     b"x = " + b"[" * 3000 + b"]" * 3000):
            self.assertTrue(C.parse_control(data)["paused"], data[:20])

    def test_reads_through_api_not_raw_cdn(self):
        api = FakeAPI({C.CONTROL_API_PATH: control_blob("paused = false\n")})
        api.get = mock.Mock(wraps=api.get)
        self.assertEqual(C.fetch_control(api), {"paused": False, "reason": ""})
        api.get.assert_called_once_with("/repos/few-shots/few-shots/contents/control.toml", {"ref": "main"})

    def test_fetch_failure_or_bad_payload_is_paused(self):
        with mock.patch.object(F.urllib.request, "urlopen", side_effect=OSError("offline")):
            self.assertTrue(C.fetch_control()["paused"])
        for payload in ({"type": "dir"}, {"type": "file", "encoding": "none", "content": "x"}, [], None,
                        {"type": "file", "encoding": "base64", "content": "测试"}):
            self.assertTrue(C.fetch_control(FakeAPI({C.CONTROL_API_PATH: payload}))["paused"], payload)

    def test_retries_without_token_when_token_is_refused(self):
        refused = F.GitHubAPI("t")
        with mock.patch.object(F.GitHubAPI, "get", autospec=True) as get:
            get.side_effect = lambda self, path, params=None: (
                (_ for _ in ()).throw(F.GitHubAPIError(403)) if self.token else control_blob("paused = false\n"))
            self.assertEqual(C.fetch_control(refused), {"paused": False, "reason": ""})
            get.side_effect = F.GitHubAPIError(403)
            self.assertTrue(C.fetch_control(refused)["paused"])

    def test_canonical_location_is_fixed(self):
        self.assertEqual((C.CONTROL_API_PATH, C.CONTROL_REF),
                         ("/repos/few-shots/few-shots/contents/control.toml", "main"))

    def test_committed_switch_parses_unpaused(self):
        self.assertEqual(C.parse_control((ROOT / "control.toml").read_bytes()), {"paused": False, "reason": ""})


if __name__ == "__main__":
    unittest.main()
