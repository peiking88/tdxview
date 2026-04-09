#!/bin/bash

# 脚本用于清理Git历史中的敏感信息

echo "正在清理Git历史中的敏感信息..."

# 备份当前状态
echo "备份当前分支..."
git branch backup-master

# 创建一个临时分支来重写历史
echo "创建临时分支..."
git checkout --orphan temp-branch

# 添加所有文件（除了.gitignore中的文件）
echo "添加文件到临时分支..."
git add -A

# 提交
echo "提交到临时分支..."
git commit -m "Initial commit: Clean history without sensitive information"

# 删除master分支
echo "删除原master分支..."
git branch -D master

# 重命名临时分支为master
echo "重命名临时分支为master..."
git branch -m master

echo "历史清理完成。现在可以强制推送到远程仓库："
echo "git push -f origin master"