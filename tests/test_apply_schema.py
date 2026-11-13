import unittest
from scripts.apply_schema import split_cypher_statements

class ApplySchemaParserTests(unittest.TestCase):
    def test_ignores_comments_and_splits_statements(self):
        source = """
        // comentário inicial;
        CREATE CONSTRAINT a IF NOT EXISTS FOR (n:A) REQUIRE n.id IS UNIQUE;
        // comentário intermediário
        CREATE INDEX b IF NOT EXISTS FOR (n:B) ON (n.name);
        """
        self.assertEqual(
            split_cypher_statements(source),
            [
                "CREATE CONSTRAINT a IF NOT EXISTS FOR (n:A) REQUIRE n.id IS UNIQUE",
                "CREATE INDEX b IF NOT EXISTS FOR (n:B) ON (n.name)",
            ],
        )

    def test_empty_source_and_comments_produce_no_statements(self):
        self.assertEqual(split_cypher_statements(" // only comment;\n"), [])
        self.assertEqual(split_cypher_statements(""), [])

if __name__ == "__main__":
    unittest.main()
