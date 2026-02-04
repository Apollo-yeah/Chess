module.exports = {
  plugins: [
    // 新增：添加react-hooks插件
    'react-hooks'
  ],
  rules: {
    // 新增：启用react-hooks的核心规则
    'react-hooks/rules-of-hooks': 'error', // 检查hooks的使用规则
    'react-hooks/exhaustive-deps': 'warn' // 检查依赖数组（设为warn，避免严格报错）
  }
};