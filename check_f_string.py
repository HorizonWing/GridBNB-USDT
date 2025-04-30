"""检查f-string模板语法"""

def test_basic_f_string():
    name = "Tester"
    print(f"Hello, {name}!")

def test_escaped_braces():
    print(f"This is a {{ literal }} not a placeholder")

def test_javascript_like_syntax():
    # Python f-string中的JavaScript样式代码
    test = """
    <script>
        function testFunc() {
            const x = 5;
            return `Value is ${x}`;
        }
    </script>
    """
    print(test)

if __name__ == "__main__":
    test_basic_f_string()
    test_escaped_braces()
    test_javascript_like_syntax()
    print("All tests passed!") 