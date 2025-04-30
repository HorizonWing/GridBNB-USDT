"""修复web_server.py文件中JavaScript模板字符串中的大括号问题"""
import re

def fix_js_templates(content):
    """修复JavaScript模板字符串中的大括号问题"""
    # 将JavaScript模板字符串中的${...}转换为${{...}}
    # 注意：此模式只会在<script>标签内和反引号之间查找${...}
    pattern = r'(`[^`]*\${)([^}]+)(}[^`]*`)'
    fixed_content = re.sub(pattern, r'\1{\2}\3', content)
    return fixed_content

def process_file(filename):
    """处理文件并修复JavaScript模板字符串"""
    # 读取文件内容
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 修复JavaScript模板字符串
    fixed_content = fix_js_templates(content)
    
    # 替换所有可能的问题点
    fixed_content = fixed_content.replace('${', '${{').replace('}', '}}')
    # 但不影响Python的f-string
    fixed_content = fixed_content.replace('{{{', '{').replace('}}}', '}')
    
    # 将修复后的内容写回文件
    with open(filename + '.fixed', 'w', encoding='utf-8') as f:
        f.write(fixed_content)
    
    print(f"已修复文件: {filename}.fixed")

if __name__ == "__main__":
    # 处理文件
    process_file('web_server.py') 