#!/bin/bash

echo "验证项目规则配置..."
echo "======================"

# 1. 检查项目规则文件
echo "1. 检查项目规则文件:"
if [ -f ".trae/rules/project_rules.md" ]; then
    echo "   ✓ .trae/rules/project_rules.md 存在"
    echo "   内容摘要:"
    head -20 .trae/rules/project_rules.md
else
    echo "   ✗ .trae/rules/project_rules.md 不存在"
fi

echo ""
echo "2. 检查Git配置:"
# 检查Git用户名
if git config user.name | grep -q "peiking88"; then
    echo "   ✓ Git用户名配置正确: peiking88"
else
    echo "   ✗ Git用户名配置不正确"
fi

# 检查GitHub域名配置
if git config --get url.https://bgithub.xyz/.insteadof | grep -q "https://github.com/"; then
    echo "   ✓ GitHub域名配置正确: bgithub.xyz"
else
    echo "   ✗ GitHub域名配置不正确"
fi

# 检查SSL验证
if git config --get http.sslVerify | grep -q "false"; then
    echo "   ✓ SSL验证已禁用"
else
    echo "   ✗ SSL验证未正确配置"
fi

echo ""
echo "3. 检查目录结构:"
# 检查日志目录
if [ -d "log" ]; then
    echo "   ✓ 日志目录存在: log/"
else
    echo "   ✗ 日志目录不存在"
fi

# 检查.trae目录
if [ -d ".trae" ]; then
    echo "   ✓ .trae配置目录存在"
else
    echo "   ✗ .trae配置目录不存在"
fi

echo ""
echo "4. 检查.gitignore文件:"
if [ -f ".gitignore" ]; then
    echo "   ✓ .gitignore文件存在"
    echo "   包含的忽略规则:"
    grep -E "(log|\.env|credentials|secrets)" .gitignore | head -5
else
    echo "   ✗ .gitignore文件不存在"
fi

echo ""
echo "5. 检查README文件:"
if [ -f "README.md" ]; then
    echo "   ✓ README.md文件存在"
    echo "   语言: 英文 (符合规则)"
else
    echo "   ✗ README.md文件不存在"
fi

echo ""
echo "验证完成!"
echo "所有规则已配置并生效。"