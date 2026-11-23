import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from utils.county_table import DESCRIPTION, build_rows, render, update_mapping_messages


def message(content, author_id=1):
    return SimpleNamespace(
        content=content,
        author=SimpleNamespace(id=author_id),
        edit=AsyncMock(),
        delete=AsyncMock(),
    )


class Channel:
    def __init__(self, messages):
        self.messages = messages
        self.send = AsyncMock()

    async def history(self, *, limit, oldest_first):
        assert limit is None and oldest_first
        for item in self.messages:
            yield item


class CountyTableTests(unittest.TestCase):
    @patch("utils.county_table.load_region_config")
    def test_single_and_multi_region_forum_links(self, load_config):
        load_config.return_value = (
            {"greater-augusta": ["Richmond"], "north": ["Fulton"], "south": ["Clayton"]},
            {"Augusta Area": ["greater-augusta"], "Metro Atlanta": ["north", "south"]},
        )
        rows = build_rows()
        self.assertIn(
            ("Richmond", "greater-augusta", "greater-augusta-chat", "greater-augusta-rba"),
            rows,
        )
        self.assertIn(("Fulton", "north", "north-chat", "metro-atlanta-rba"), rows)
        self.assertIn(("Clayton", "south", "south-chat", "metro-atlanta-rba"), rows)
        result = "".join(render(rows, {}, {"greater-augusta-rba": 123}))
        self.assertIn("**Richmond**: @greater-augusta | #greater-augusta-chat | <#123>", result)
        self.assertIn("**Fulton**: @north | #north-chat | #metro-atlanta-rba", result)


class UpdateMappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_updates_mapping_only_and_suppresses_mentions(self):
        old_header = message("**County to channel mapping**\nOld description")
        old_row = message("- **Fulton**: <@&1> | <#2> | <#3>\n")
        foreign = message("- **Fulton**: <@&1> | <#2> | <#3>\n", author_id=2)
        unrelated = message("An unrelated message")
        channel = Channel([old_header, foreign, old_row, unrelated])
        row = "- **Fulton**: <@&4> | <#2> | <#3>\n"
        added = "- **Gwinnett**: @region | #chat | #forum\n"

        await update_mapping_messages(channel, 1, [DESCRIPTION, row, added])

        old_header.edit.assert_awaited_once()
        old_row.edit.assert_awaited_once()
        channel.send.assert_awaited_once()
        for call in (old_header.edit.await_args, old_row.edit.await_args, channel.send.await_args):
            self.assertEqual(call.kwargs["allowed_mentions"].to_dict(), {"parse": []})
        self.assertEqual(old_row.edit.await_args.kwargs["content"], row)
        self.assertEqual(channel.send.await_args.args[0], added)
        foreign.edit.assert_not_awaited()
        foreign.delete.assert_not_awaited()
        unrelated.delete.assert_not_awaited()

    async def test_unchanged_and_surplus_messages(self):
        header = message(DESCRIPTION)
        row = message("- **Fulton**: <@&1> | <#2> | <#3>\n")
        surplus = message("- **Gwinnett**: @region | #chat | #forum\n")
        channel = Channel([header, row, surplus])

        await update_mapping_messages(channel, 1, [DESCRIPTION, row.content])

        header.edit.assert_not_awaited()
        row.edit.assert_not_awaited()
        channel.send.assert_not_awaited()
        surplus.delete.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
