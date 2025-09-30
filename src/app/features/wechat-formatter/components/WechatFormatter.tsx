'use client';

import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ApiSettings, { ApiProvider } from '../../../components/ApiSettings';

type Theme = {
  name: string;
  style: Record<string, string>;
}

const defaultThemes: Theme[] = [
  {
    name: 'Default',
    style: {
      fontFamily: '-apple-system, BlinkMacSystemFont, Helvetica Neue, PingFang SC, Hiragino Sans GB, Microsoft YaHei UI, Microsoft YaHei, Arial, sans-serif',
      color: '#333',
      lineHeight: '1.75',
      background: '#fff',
      h1: 'font-size: 24px; font-weight: bold; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-top: 30px;',
      h2: 'font-size: 20px; font-weight: bold; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 20px;',
      h3: 'font-size: 18px; font-weight: bold; margin-top: 15px;',
      p: 'margin: 10px 0; line-height: 1.75;',
      a: 'color: #0366d6; text-decoration: none;',
      code: 'background-color: rgba(27,31,35,.05); border-radius: 3px; font-size: 85%; margin: 0; padding: 0.2em 0.4em;',
      pre: 'background-color: #f6f8fa; border-radius: 3px; font-size: 85%; line-height: 1.45; overflow: auto; padding: 16px;',
      blockquote: 'border-left: 4px solid #dfe2e5; color: #6a737d; padding: 0 1em;',
      img: 'max-width: 100%; box-sizing: content-box;',
    }
  },
  {
    name: 'Clean',
    style: {
      fontFamily: 'Georgia, serif',
      color: '#2c3e50',
      lineHeight: '1.8',
      background: '#fff',
      h1: 'font-size: 26px; font-weight: 600; margin-top: 30px; font-family: -apple-system, BlinkMacSystemFont, sans-serif;',
      h2: 'font-size: 22px; font-weight: 600; margin-top: 25px; font-family: -apple-system, BlinkMacSystemFont, sans-serif;',
      h3: 'font-size: 18px; font-weight: 600; margin-top: 20px; font-family: -apple-system, BlinkMacSystemFont, sans-serif;',
      p: 'margin: 12px 0; line-height: 1.8;',
      a: 'color: #1a73e8; text-decoration: none; border-bottom: 1px solid #d3e3fd;',
      code: 'background-color: #f1f3f4; border-radius: 3px; font-size: 85%; margin: 0; padding: 0.2em 0.4em;',
      pre: 'background-color: #f8f9fa; border-radius: 4px; font-size: 85%; line-height: 1.5; overflow: auto; padding: 16px;',
      blockquote: 'border-left: 3px solid #dbdfe4; color: #606770; padding: 0 16px; font-style: italic;',
      img: 'max-width: 100%; border-radius: 4px;',
    }
  },
  {
    name: '科技资讯',
    style: {
      fontFamily: 'SF Pro Display, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
      color: '#222',
      lineHeight: '1.7',
      background: '#fff',
      h1: 'font-size: 26px; font-weight: 600; color: #0a84ff; margin-top: 32px; margin-bottom: 16px;',
      h2: 'font-size: 22px; font-weight: 600; color: #333; border-left: 4px solid #0a84ff; padding-left: 10px; margin-top: 24px; margin-bottom: 12px;',
      h3: 'font-size: 18px; font-weight: 600; color: #444; margin-top: 20px; margin-bottom: 10px;',
      p: 'margin: 12px 0; line-height: 1.8; letter-spacing: 0.02em;',
      a: 'color: #0a84ff; text-decoration: none; border-bottom: 1px solid rgba(10, 132, 255, 0.3);',
      code: 'background-color: #f1f2f6; border-radius: 3px; font-family: "SFMono-Regular", Consolas, monospace; font-size: 85%; padding: 0.2em 0.4em; color: #e83e8c;',
      pre: 'background-color: #f8f9fa; border-radius: 5px; padding: 16px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05);',
      blockquote: 'border-left: 4px solid #0a84ff; background-color: rgba(10, 132, 255, 0.05); padding: 12px 16px; color: #555; margin: 16px 0;',
      img: 'max-width: 100%; border-radius: 6px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);',
    }
  },
  {
    name: '商务职场',
    style: {
      fontFamily: '"Noto Sans SC", -apple-system, BlinkMacSystemFont, sans-serif',
      color: '#333',
      lineHeight: '1.75',
      background: '#fff',
      h1: 'font-size: 26px; font-weight: 600; color: #23395b; margin-top: 32px; margin-bottom: 16px; border-bottom: 1px solid #eee; padding-bottom: 12px;',
      h2: 'font-size: 22px; font-weight: 600; color: #34558b; margin-top: 28px; margin-bottom: 14px;',
      h3: 'font-size: 18px; font-weight: 600; color: #445e93; margin-top: 24px; margin-bottom: 12px;',
      p: 'margin: 14px 0; line-height: 1.8; color: #444;',
      a: 'color: #336699; text-decoration: none; font-weight: 500;',
      code: 'background-color: #f5f7fa; border-radius: 3px; font-size: 85%; padding: 0.2em 0.4em; color: #555;',
      pre: 'background-color: #f8f9fa; border-radius: 4px; padding: 16px; border: 1px solid #eee;',
      blockquote: 'border-left: 4px solid #6a89cc; padding: 10px 16px; color: #555; background-color: #f8f9fa; margin: 16px 0; font-size: 15px;',
      img: 'max-width: 100%; border-radius: 4px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);',
    }
  },
  {
    name: '教育学术',
    style: {
      fontFamily: '"Source Han Serif SC", "Noto Serif SC", "Songti SC", serif',
      color: '#333',
      lineHeight: '1.9',
      background: '#fcfcfc',
      h1: 'font-size: 26px; font-weight: 600; color: #003366; text-align: center; margin-top: 32px; margin-bottom: 20px;',
      h2: 'font-size: 22px; font-weight: 600; color: #004080; margin-top: 28px; margin-bottom: 16px; border-bottom: 1px solid #efefef; padding-bottom: 8px;',
      h3: 'font-size: 18px; font-weight: 600; color: #005599; margin-top: 24px; margin-bottom: 12px;',
      p: 'margin: 16px 0; line-height: 2.0; text-align: justify; letter-spacing: 0.02em;',
      a: 'color: #0066cc; text-decoration: none; border-bottom: 1px dashed #0066cc;',
      code: 'background-color: #f5f5f5; border-radius: 3px; font-size: 85%; padding: 0.2em 0.4em; color: #333; font-family: Consolas, monospace;',
      pre: 'background-color: #f8f8f8; border-radius: 4px; padding: 16px; border: 1px solid #eee; font-family: Consolas, monospace;',
      blockquote: 'border-left: 4px solid #99b3cc; background-color: #f9f9f9; padding: 12px 16px; color: #444; margin: 16px 0; font-style: italic;',
      img: 'max-width: 100%; display: block; margin: 20px auto; border: 1px solid #eee;',
    }
  },
  {
    name: '生活时尚',
    style: {
      fontFamily: '"PingFang SC", -apple-system, BlinkMacSystemFont, sans-serif',
      color: '#333',
      lineHeight: '1.8',
      background: '#fff',
      h1: 'font-size: 26px; font-weight: normal; color: #ff6b6b; text-align: center; margin-top: 32px; margin-bottom: 20px; letter-spacing: 1px;',
      h2: 'font-size: 22px; font-weight: normal; color: #ff6b6b; margin-top: 28px; margin-bottom: 16px; letter-spacing: 0.5px;',
      h3: 'font-size: 18px; font-weight: normal; color: #ff8787; margin-top: 24px; margin-bottom: 12px;',
      p: 'margin: 14px 0; line-height: 1.9; color: #555; letter-spacing: 0.03em;',
      a: 'color: #ff6b6b; text-decoration: none; border-bottom: 1px solid #ff6b6b;',
      code: 'background-color: #fff0f0; border-radius: 3px; font-size: 85%; padding: 0.2em 0.4em; color: #ff6b6b;',
      pre: 'background-color: #fff8f8; border-radius: 8px; padding: 16px; border: 1px solid #ffeeee;',
      blockquote: 'border-left: 4px solid #ffaaaa; background-color: #fff8f8; padding: 12px 16px; color: #666; margin: 16px 0;',
      img: 'max-width: 100%; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);',
    }
  },
  {
    name: '文学历史',
    style: {
      fontFamily: '"FangSong", "STFangsong", "KaiTi", "STKaiti", serif',
      color: '#333',
      lineHeight: '2.0',
      background: '#fffcf5',
      h1: 'font-size: 28px; font-weight: normal; color: #8d6e63; margin-top: 32px; margin-bottom: 20px; text-align: center; letter-spacing: 2px;',
      h2: 'font-size: 24px; font-weight: normal; color: #795548; margin-top: 28px; margin-bottom: 16px; letter-spacing: 1px;',
      h3: 'font-size: 20px; font-weight: normal; color: #6d4c41; margin-top: 24px; margin-bottom: 12px;',
      p: 'margin: 16px 0; line-height: 2.2; text-align: justify; letter-spacing: 0.05em; text-indent: 2em;',
      a: 'color: #795548; text-decoration: none; border-bottom: 1px solid rgba(121, 85, 72, 0.3);',
      code: 'background-color: #f5f1e9; border-radius: 3px; font-size: 85%; padding: 0.2em 0.4em; color: #6d4c41; font-family: Consolas, monospace;',
      pre: 'background-color: #f8f5f0; border-radius: 4px; padding: 16px; border: 1px solid #eee8dd;',
      blockquote: 'border-left: 4px solid #bcaaa4; background-color: #f8f5f0; padding: 12px 16px; color: #5d4037; margin: 16px 0; font-style: italic;',
      img: 'max-width: 100%; display: block; margin: 20px auto; border: 8px solid white; box-shadow: 0 4px 12px rgba(0,0,0,0.1);',
    }
  }
];

const defaultReadmeContent = `# AI 写作助手

一个基于 Next.js 构建的 AI 写作助手，帮助用户组织写作风格提示词，并通过大型语言模型（LLM）生成高质量内容。适用于作家、内容创作者、学生和需要创作文案的专业人员。

## 🌟 核心功能

### 📝 写作助手
- **智能内容生成**：根据主题、关键词和字数要求快速生成高质量文章
- **深度风格定制**：多维度提示词风格编辑器，精确控制语言、结构、叙述、情感等风格元素
- **实时编辑**：在内置的编辑器中直接编辑、修改生成的内容
- **导出功能**：一键导出为Markdown格式，便于后续使用

### 🔄 AI文本优化器
- **AI特征去除**：去除AI生成文本特征，使内容更自然、更人性化
- **检测对抗**：专门针对GPTZero等AI检测器使用的统计学特征进行优化
- **统计特征优化**：特别针对困惑度(Perplexity)和突发性(Burstiness)两项关键指标进行优化
- **多种优化预设**：包括"人类写作特征优化"和"AI修改指导"两种预设模式
- **自定义指令**：支持自定义洗稿指令，满足个性化需求

## 🚀 技术特点

- **多LLM支持**：兼容OpenAI、Grok、Ollama、DeepSeek等多种API
- **API灵活配置**：简单直观的API设置界面，便于切换不同的模型和服务
- **长超时支持**：针对大型文本处理优化的后端，最长支持10分钟请求超时
- **响应式设计**：完美适配桌面和移动设备的现代化UI
- **错误处理**：友好的错误提示和详细的技术调试信息

## 🛠️ 快速开始

确保已安装 Node.js 16.20.0 或更高版本。

### 安装依赖

\`\`\`bash
npm install
\`\`\`

### 启动开发服务器

\`\`\`bash
npm run dev
\`\`\`

访问 [http://localhost:3000](http://localhost:3000) 开始使用。

### 预览
#### 写作助手
![preview](https://raw.githubusercontent.com/GeekyWizKid/writing-helper/main/preview/preview.jpg)
#### AI文本优化
![preview](https://raw.githubusercontent.com/GeekyWizKid/writing-helper/main/preview/xigao_01.png)
![preview](https://raw.githubusercontent.com/GeekyWizKid/writing-helper/main/preview//xigao_02.png)

## 📝 使用指南

### 写作助手

1. **设置主题和关键词**：
   - 输入文章主题
   - 添加关键词（用"、"分隔）
   - 设定目标字数

2. **自定义写作风格**：
   - 点击"风格编辑器"打开详细设置
   - 调整语言风格、结构、叙述视角、情感表达等
   - 添加个性化要素如标志性短语、文化引用等

3. **API设置**：
   - 选择API提供商（OpenAI、Grok、Ollama、DeepSeek等）
   - 输入API密钥
   - 选择合适的模型

4. **生成与导出**：
   - 点击"生成内容"
   - 在编辑器中查看和修改内容
   - 使用"导出为Markdown"保存

### AI文本优化器

1. **选择API设置**：
   - 配置与上述相同的API选项

2. **输入文本**：
   - 粘贴需要优化的文本

3. **选择优化模式**：
   - "人类写作特征优化"：全面优化七大写作特征
   - "AI修改指导"：分析并生成个性化改写策略
   - 或使用自定义优化指令

4. **处理文本**：
   - 点击"优化文本"按钮
   - 查看处理结果
   - 复制优化后的内容

## 🔌 支持的API

本应用支持多种LLM服务的API：

- **OpenAI**：GPT-4和GPT-3.5系列
- **Grok**：xAI的Grok-2系列模型
- **Ollama**：适用于本地运行的开源模型
- **DeepSeek**：DeepSeek系列模型
- **自定义API**：支持配置其他兼容接口

## 📋 开发路线图

- [ ] 文本摘要功能
- [ ] 内容历史记录
- [ ] 更多LLM支持（Claude、Gemini等）
- [ ] 文档翻译工具
- [ ] 文章风格分析

## ⚠️ 免责声明

- 本工具生成的内容由使用者自行负责
- 使用本工具需遵守相关API服务的使用条款
- 不得用于生成违法、不实或有害内容
- 对于API服务的可用性或费用不承担责任

## 📄 许可证

本项目采用 [MIT 许可证](./LICENSE)。

## 📧 联系方式

如有问题或建议，请通过GitHub Issues联系我们。`;

export default function WechatFormatter() {
  const [markdown, setMarkdown] = useState<string>(defaultReadmeContent);
  const [theme, setTheme] = useState<Theme>(defaultThemes[0]);
  const [customCSS, setCustomCSS] = useState<string>('');
  const [showPreview, setShowPreview] = useState<boolean>(true);
  const previewRef = useRef<HTMLDivElement>(null);
  
  // AI 生成 CSS 相关状态
  const [styleDescription, setStyleDescription] = useState<string>('');
  const [isGeneratingStyle, setIsGeneratingStyle] = useState<boolean>(false);
  const [styleError, setStyleError] = useState<string | null>(null);
  const [showApiSettings, setShowApiSettings] = useState<boolean>(false);
  
  // API 设置状态
  const [apiProvider, setApiProvider] = useState<ApiProvider>('openai');
  const [apiUrl, setApiUrl] = useState<string>('https://api.openai.com/v1/chat/completions');
  const [apiKey, setApiKey] = useState<string>('');
  const [model, setModel] = useState<string>('gpt-4');
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  // 添加Markdown语法示例/帮助
  const [showMarkdownHelp, setShowMarkdownHelp] = useState<boolean>(false);
  // 添加表格生成器状态
  const [showTableGenerator, setShowTableGenerator] = useState<boolean>(false);
  const [tableRows, setTableRows] = useState<number>(3);
  const [tableCols, setTableCols] = useState<number>(3);
  // 添加编辑历史记录状态
  const [markdownHistory, setMarkdownHistory] = useState<string[]>([]);
  const [currentHistoryIndex, setCurrentHistoryIndex] = useState<number>(-1);

  // API 设置切换
  const toggleApiSettings = () => {
    setShowApiSettings(!showApiSettings);
  };

  // 获取 Ollama 模型列表
  const fetchOllamaModels = async (): Promise<string[] | void> => {
    if (apiProvider !== 'ollama') return;
    
    try {
      const response = await fetch('/api/proxy/ollama-models', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ollamaUrl: apiUrl.replace('/api/generate', '/api/tags'),
        }),
      });
      
      if (!response.ok) {
        throw new Error(`获取模型失败: ${response.status}`);
      }
      
      const data = await response.json();
      if (data.models && Array.isArray(data.models)) {
        const modelNames = data.models.map((model: { name?: string; model?: string }) => model.name || model.model || '');
        setAvailableModels(modelNames);
        return modelNames;
      }
      return [];
    } catch (error) {
      console.error('获取 Ollama 模型错误:', error);
      return [];
    }
  };

  // 获取 Cherry Server 模型列表
  const fetchCherryModels = async (): Promise<string[] | void> => {
    if (apiProvider !== 'cherry') return;
    if (!apiKey) {
      setStyleError('Cherry Server 需要 API 密钥以获取模型列表');
      return [];
    }
    try {
      const response = await fetch('/api/proxy/cherry-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          serverUrl: 'http://localhost:23333/v1/models',
          apiKey
        }),
      });
      if (!response.ok) {
        throw new Error(`获取模型失败: ${response.status}`);
      }
      const data = await response.json();
      let modelNames: string[] = [];
      if (data.models && Array.isArray(data.models)) {
        modelNames = data.models.filter((s: unknown) => typeof s === 'string') as string[];
      } else if (data && typeof data === 'object' && Array.isArray((data as { data?: unknown[] }).data)) {
        const list = ((data as { data?: unknown[] }).data || []) as unknown[];
        modelNames = list.map((item) => {
          const obj = item as Record<string, unknown>;
          return typeof obj?.id === 'string' ? (obj.id as string) : '';
        }).filter(Boolean);
      }
      setAvailableModels(modelNames);
      return modelNames;
    } catch (error) {
      console.error('获取 Cherry 模型错误:', error);
      return [];
    }
  };

  const fetchAvailableModels = async () => {
    if (apiProvider === 'ollama') return fetchOllamaModels();
    if (apiProvider === 'cherry') return fetchCherryModels();
    return [] as string[];
  };
  
  // 使用 AI 生成 CSS 样式
  const generateAIStyle = async () => {
    if (!styleDescription.trim()) {
      setStyleError('请输入样式描述');
      return;
    }
    
    setIsGeneratingStyle(true);
    setStyleError(null);
    
    try {
      // 检测API提供商类型
      const isGrokApi = apiUrl.includes('grok') || apiUrl.includes('xai');
      const isOllamaApi = apiUrl.includes('ollama') || apiUrl.includes('11434');
      const isDeepSeekApi = apiUrl.includes('deepseek');
      
      // 构建提示词
      const prompt = `
我需要一套适用于微信公众号文章的CSS样式，风格描述: ${styleDescription}。
请生成CSS代码，包含以下元素的样式：
1. h1, h2, h3 (标题样式)
2. p (段落样式)
3. a (链接样式)
4. code (行内代码样式)
5. pre (代码块样式)
6. blockquote (引用块样式)
7. 颜色方案（主色、背景色、文字颜色）
8. 字体设置

请只返回CSS代码，不要有任何解释或前导文字。以下是CSS选择器的提示:
.wechat-preview h1 {}
.wechat-preview h2 {}
.wechat-preview h3 {}
.wechat-preview p {}
.wechat-preview a {}
.wechat-preview code {}
.wechat-preview pre {}
.wechat-preview blockquote {}
`;
      
      // 准备请求体
      let requestBody: Record<string, unknown>;
      let isOllama = false;
      
      if (isOllamaApi) {
        requestBody = {
          model: model || 'llama2',
          prompt,
          stream: false
        };
        isOllama = true;
      } else if (isGrokApi) {
        requestBody = {
          messages: [{ role: 'user', content: prompt }],
          model: model || 'grok-3-latest',
          temperature: 0.7,
          stream: false
        };
      } else if (isDeepSeekApi) {
        requestBody = {
          model: model || 'deepseek-chat',
          messages: [{ role: 'user', content: prompt }],
          temperature: 0.7,
          stream: false
        };
      } else {
        requestBody = {
          model: model || 'gpt-4',
          messages: [{ role: 'user', content: prompt }],
          temperature: 0.7
        };
      }
      
      // 准备请求头
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      
      if (!isOllamaApi && apiKey) {
        headers['Authorization'] = `Bearer ${apiKey}`;
      }
      
      console.log('正在发送AI样式生成请求:', {
        targetUrl: apiUrl,
        provider: apiProvider,
        model: model,
        styleDescription: styleDescription
      });
      
      // 发送代理请求
      const proxyResponse = await fetch('/api/proxy', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          targetUrl: apiUrl,
          headers,
          body: requestBody,
          isOllama
        })
      });
      
      if (!proxyResponse.ok) {
        const errorData = await proxyResponse.json().catch(() => ({ error: { message: `代理服务错误: ${proxyResponse.status}` } }));
        throw new Error(errorData.error?.message || `代理服务错误: ${proxyResponse.status}`);
      }
      
      const data = await proxyResponse.json();
      console.log('AI样式生成响应:', data);
      
      // 提取生成的 CSS
      let generatedCSS = '';
      
      if (data.choices && data.choices.length > 0 && data.choices[0].message && data.choices[0].message.content) {
        generatedCSS = data.choices[0].message.content;
      } else if (data.message && data.message.content) {
        generatedCSS = data.message.content;
      } else if (data.content) {
        generatedCSS = data.content;
      } else if (data.output) {
        generatedCSS = data.output;
      } else if (data.response) {
        generatedCSS = data.response;
      } else if (data.text) {
        generatedCSS = data.text;
      } else if (typeof data === 'string') {
        generatedCSS = data;
      } else {
        throw new Error('无法从API响应中提取内容');
      }
      
      // 提取代码块中的 CSS
      const cssMatch = generatedCSS.match(/```(?:css)?([\s\S]+?)```/);
      if (cssMatch && cssMatch[1]) {
        generatedCSS = cssMatch[1].trim();
      }
      
      console.log('提取的CSS样式:', generatedCSS);
      
      // 更新自定义 CSS
      setCustomCSS(generatedCSS);
      
      // 显示成功提示
      alert('AI样式生成成功，已应用到编辑器！');
    } catch (error) {
      console.error('生成 CSS 样式失败:', error);
      setStyleError(error instanceof Error ? error.message : '生成样式失败');
    } finally {
      setIsGeneratingStyle(false);
    }
  };

  // Apply styling to the preview
  useEffect(() => {
    if (previewRef.current) {
      const styleElement = document.createElement('style');
      
      let css = `
        .wechat-preview {
          font-family: ${theme.style.fontFamily};
          color: ${theme.style.color};
          line-height: ${theme.style.lineHeight};
          background: ${theme.style.background};
          padding: 16px;
          max-width: 800px;
          margin: 0 auto;
          border: 1px solid #e0e0e0;
          border-radius: 8px;
        }
        .wechat-preview h1 { ${theme.style.h1} }
        .wechat-preview h2 { ${theme.style.h2} }
        .wechat-preview h3 { ${theme.style.h3} }
        .wechat-preview p { ${theme.style.p} }
        .wechat-preview a { ${theme.style.a} }
        .wechat-preview code { ${theme.style.code} }
        .wechat-preview pre { ${theme.style.pre} }
        .wechat-preview blockquote { ${theme.style.blockquote} }
        .wechat-preview img { ${theme.style.img} }
        .wechat-preview .image-wrapper { text-align: center; margin: 16px 0; }
        .wechat-preview .image-wrapper img { max-width: 100%; }
      `;

      // Add custom CSS
      if (customCSS) {
        css += customCSS;
      }
      
      styleElement.textContent = css;
      document.head.appendChild(styleElement);
      
      return () => {
        document.head.removeChild(styleElement);
      };
    }
  }, [theme, customCSS]);

  const copyToClipboard = async () => {
    if (previewRef.current) {
      try {
        await navigator.clipboard.writeText(previewRef.current.innerHTML);
        alert('已复制到剪贴板，可直接粘贴到微信公众号编辑器');
      } catch (err) {
        console.error('无法复制内容: ', err);
        alert('复制失败，请手动复制');
      }
    }
  };

  // 添加自适应文本区域的ref和处理函数
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 添加自适应高度的useEffect
  useEffect(() => {
    const adjustHeight = () => {
      const textarea = textareaRef.current;
      if (textarea) {
        // 重置高度以获取准确的scrollHeight
        textarea.style.height = 'auto';
        // 设置为内容高度
        textarea.style.height = `${textarea.scrollHeight}px`;
      }
    };
    
    // 初始化时调整高度
    adjustHeight();
    
    // 创建一个ResizeObserver以监听窗口大小变化
    const resizeObserver = new ResizeObserver(() => {
      adjustHeight();
    });
    
    if (textareaRef.current) {
      resizeObserver.observe(textareaRef.current);
    }
    
    // 清理
    return () => {
      if (textareaRef.current) {
        resizeObserver.unobserve(textareaRef.current);
      }
      resizeObserver.disconnect();
    };
  }, [markdown]); // 当内容变化时重新调整高度

  // 创建自定义表格
  const generateTable = () => {
    if (!textareaRef.current) return;
    
    const headerRow = Array(tableCols).fill('').map((_, i) => `表头${i+1}`).join(' | ');
    const separatorRow = Array(tableCols).fill('-----').join(' | ');
    const contentRows = Array(tableRows).fill('').map((_, rowIdx) => {
      return Array(tableCols).fill('').map((_, colIdx) => `内容${rowIdx*tableCols+colIdx+1}`).join(' | ');
    }).join('\n| ');
    
    const tableMarkdown = `
| ${headerRow} |
| ${separatorRow} |
| ${contentRows} |
`;
    
    insertMarkdown('customtable', tableMarkdown);
    setShowTableGenerator(false);
  };

  // 添加撤销功能
  const undoEdit = () => {
    if (currentHistoryIndex > 0) {
      const newIndex = currentHistoryIndex - 1;
      setCurrentHistoryIndex(newIndex);
      setMarkdown(markdownHistory[newIndex]);
    }
  };

  // 保存编辑历史
  const saveHistory = (newText: string) => {
    // 如果当前不是历史记录的最后一个，截断历史记录
    if (currentHistoryIndex < markdownHistory.length - 1) {
      const newHistory = markdownHistory.slice(0, currentHistoryIndex + 1);
      setMarkdownHistory([...newHistory, newText]);
    } else {
      // 否则直接添加到历史记录
      setMarkdownHistory([...markdownHistory, newText]);
    }
    setCurrentHistoryIndex(markdownHistory.length);
  };

  // 扩展insertMarkdown函数以支持自定义表格
  const insertMarkdown = (type: string, customContent?: string) => {
    if (!textareaRef.current) return;
    
    const textarea = textareaRef.current;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = textarea.value.substring(start, end);
    const beforeText = textarea.value.substring(0, start);
    const afterText = textarea.value.substring(end);
    
    let insertion = '';
    
    switch(type) {
      case 'bold':
        insertion = `**${selectedText || '加粗文字'}**`;
        break;
      case 'italic':
        insertion = `*${selectedText || '斜体文字'}*`;
        break;
      case 'heading1':
        insertion = `\n# ${selectedText || '一级标题'}\n`;
        break;
      case 'heading2':
        insertion = `\n## ${selectedText || '二级标题'}\n`;
        break;
      case 'heading3':
        insertion = `\n### ${selectedText || '三级标题'}\n`;
        break;
      case 'heading4':
        insertion = `\n#### ${selectedText || '四级标题'}\n`;
        break;
      case 'heading5':
        insertion = `\n##### ${selectedText || '五级标题'}\n`;
        break;
      case 'link':
        insertion = `[${selectedText || '链接文字'}](https://example.com)`;
        break;
      case 'image':
        insertion = `![${selectedText || '图片描述'}](https://example.com/image.jpg)`;
        break;
      case 'code':
        insertion = selectedText ? `\`${selectedText}\`` : '`代码`';
        break;
      case 'codeblock':
        insertion = selectedText ? 
          `\n\`\`\`\n${selectedText}\n\`\`\`\n` : 
          '\n```\n// 在此处输入代码\n```\n';
        break;
      case 'quote':
        // 处理多行引用
        if (selectedText.includes('\n')) {
          const lines = selectedText.split('\n');
          insertion = '\n' + lines.map(line => `> ${line}`).join('\n') + '\n';
        } else {
          insertion = `\n> ${selectedText || '引用文字'}\n`;
        }
        break;
      case 'list':
        // 处理多行列表
        if (selectedText.includes('\n')) {
          const lines = selectedText.split('\n');
          insertion = '\n' + lines.map(line => `- ${line}`).join('\n') + '\n';
        } else {
          insertion = `\n- ${selectedText || '列表项'}\n`;
        }
        break;
      case 'orderedlist':
        // 处理多行有序列表
        if (selectedText.includes('\n')) {
          const lines = selectedText.split('\n');
          insertion = '\n' + lines.map((line, i) => `${i+1}. ${line}`).join('\n') + '\n';
        } else {
          insertion = `\n1. ${selectedText || '有序列表项'}\n`;
        }
        break;
      case 'table':
        setShowTableGenerator(true);
        return;
      case 'customtable':
        insertion = customContent || '';
        break;
      case 'hr':
        insertion = '\n\n---\n\n';
        break;
    }
    
    const newText = beforeText + insertion + afterText;
    
    // 保存到历史记录
    saveHistory(textarea.value);
    
    setMarkdown(newText);
    
    // 重新聚焦并设置光标位置
    setTimeout(() => {
      textarea.focus();
      const newCursorPos = start + insertion.length;
      textarea.setSelectionRange(newCursorPos, newCursorPos);
    }, 0);
  };

  // 添加Markdown语法示例/帮助
  const markdownHelpContent = (
    <div className="bg-white border border-gray-200 rounded-md p-4 mt-2 text-sm shadow-md">
      <h4 className="font-medium text-gray-800 mb-2">Markdown 语法参考</h4>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div>
          <p className="text-gray-700 mb-1"><code className="bg-gray-100 px-1 py-0.5 rounded"># 标题</code> - 一级标题</p>
          <p className="text-gray-700 mb-1"><code className="bg-gray-100 px-1 py-0.5 rounded">## 标题</code> - 二级标题</p>
          <p className="text-gray-700 mb-1"><code className="bg-gray-100 px-1 py-0.5 rounded">**文字**</code> - <strong>加粗文字</strong></p>
          <p className="text-gray-700 mb-1"><code className="bg-gray-100 px-1 py-0.5 rounded">*文字*</code> - <em>斜体文字</em></p>
          <p className="text-gray-700 mb-1"><code className="bg-gray-100 px-1 py-0.5 rounded">~~文字~~</code> - <del>删除线</del></p>
        </div>
        <div>
          <p className="text-gray-700 mb-1"><code className="bg-gray-100 px-1 py-0.5 rounded">[链接](URL)</code> - 链接</p>
          <p className="text-gray-700 mb-1"><code className="bg-gray-100 px-1 py-0.5 rounded">![描述](图片URL)</code> - 图片</p>
          <p className="text-gray-700 mb-1"><code className="bg-gray-100 px-1 py-0.5 rounded">- 项目</code> - 无序列表</p>
          <p className="text-gray-700 mb-1"><code className="bg-gray-100 px-1 py-0.5 rounded">1. 项目</code> - 有序列表</p>
          <p className="text-gray-700 mb-1"><code className="bg-gray-100 px-1 py-0.5 rounded">{`>`} 引用</code> - 引用文本</p>
        </div>
      </div>
      <div className="mt-2 text-xs text-gray-600">
        <p>点击上方工具栏按钮可快速插入对应格式</p>
      </div>
    </div>
  );

  return (
    <div className="bg-white rounded-lg shadow-sm overflow-hidden">
      <div className="p-6">
        <div className="flex flex-col gap-6">
          {/* 编辑器和预览区域 */}
          <div className="flex flex-col md:flex-row gap-6">
            {/* 左侧编辑区域 */}
            <div className="md:w-1/2 space-y-4">
              <div className="border border-gray-200 rounded-lg p-4 bg-white">
                <h3 className="text-lg font-medium mb-3 flex items-center text-gray-800">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                  Markdown 编辑
                </h3>
                
                {/* Markdown 工具栏 */}
                <div className="mb-2 flex flex-wrap gap-1 border-b border-gray-200 pb-2">
                  <button
                    type="button"
                    onClick={() => insertMarkdown('heading1')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="一级标题"
                  >
                    <span className="font-bold text-base">H1</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('heading2')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="二级标题"
                  >
                    <span className="font-bold text-base">H2</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('heading3')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="三级标题"
                  >
                    <span className="font-bold text-base">H3</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('heading4')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="四级标题"
                  >
                    <span className="font-bold text-base">H4</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('heading5')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="五级标题"
                  >
                    <span className="font-bold text-base">H5</span>
                  </button>
                  <div className="h-6 w-px bg-gray-300 mx-1"></div>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('bold')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="加粗"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M6 4h8a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z"></path>
                      <path d="M6 12h9a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z"></path>
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('italic')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="斜体"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="19" y1="4" x2="10" y2="4"></line>
                      <line x1="14" y1="20" x2="5" y2="20"></line>
                      <line x1="15" y1="4" x2="9" y2="20"></line>
                    </svg>
                  </button>
                  <div className="h-6 w-px bg-gray-300 mx-1"></div>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('list')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="无序列表"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="8" y1="6" x2="21" y2="6"></line>
                      <line x1="8" y1="12" x2="21" y2="12"></line>
                      <line x1="8" y1="18" x2="21" y2="18"></line>
                      <line x1="3" y1="6" x2="3.01" y2="6"></line>
                      <line x1="3" y1="12" x2="3.01" y2="12"></line>
                      <line x1="3" y1="18" x2="3.01" y2="18"></line>
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('orderedlist')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="有序列表"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="10" y1="6" x2="21" y2="6"></line>
                      <line x1="10" y1="12" x2="21" y2="12"></line>
                      <line x1="10" y1="18" x2="21" y2="18"></line>
                      <path d="M4 6h1v4"></path>
                      <path d="M4 10h2"></path>
                      <path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"></path>
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('quote')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="引用"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M3 8l6.697 0"></path>
                      <path d="M3 12l6.697 0"></path>
                      <path d="M3 16l6.697 0"></path>
                      <path d="M17.5 16h.5c1.667 0 3-1.5 3-3 0-1.5-1.5-3-3-3h-.5"></path>
                      <path d="M11.5 16h.5c1.667 0 3-1.5 3-3 0-1.5-1.5-3-3-3h-.5"></path>
                    </svg>
                  </button>
                  <div className="h-6 w-px bg-gray-300 mx-1"></div>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('link')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="插入链接"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
                      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('image')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="插入图片"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                      <circle cx="8.5" cy="8.5" r="1.5"></circle>
                      <polyline points="21 15 16 10 5 21"></polyline>
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('code')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="插入代码"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="16 18 22 12 16 6"></polyline>
                      <polyline points="8 6 2 12 8 18"></polyline>
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('codeblock')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="插入代码块"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7"></path>
                      <line x1="16" y1="8" x2="8" y2="16"></line>
                      <line x1="12" y1="8" x2="8" y2="12"></line>
                      <line x1="16" y1="12" x2="12" y2="16"></line>
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('table')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="插入表格"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                      <line x1="3" y1="9" x2="21" y2="9"></line>
                      <line x1="3" y1="15" x2="21" y2="15"></line>
                      <line x1="9" y1="3" x2="9" y2="21"></line>
                      <line x1="15" y1="3" x2="15" y2="21"></line>
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => insertMarkdown('hr')}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded"
                    title="插入水平线"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="5" y1="12" x2="19" y2="12"></line>
                    </svg>
                  </button>
                  {/* 添加撤销按钮 */}
                  <button
                    type="button"
                    onClick={undoEdit}
                    disabled={currentHistoryIndex <= 0}
                    className={`p-1.5 text-gray-700 hover:bg-gray-100 rounded ${currentHistoryIndex <= 0 ? 'opacity-50 cursor-not-allowed' : ''}`}
                    title="撤销"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M9 14L4 9l5-5"></path>
                      <path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5v0a5.5 5.5 0 0 1-5.5 5.5H11"></path>
                    </svg>
                  </button>
                  <div className="flex-grow"></div>
                  <button
                    type="button"
                    onClick={() => setShowMarkdownHelp(!showMarkdownHelp)}
                    className="p-1.5 text-gray-700 hover:bg-gray-100 rounded flex items-center"
                    title="Markdown 帮助"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span className="text-sm">帮助</span>
                  </button>
                </div>
                
                {/* Markdown 语法帮助 */}
                {showMarkdownHelp && markdownHelpContent}
                
                {/* 表格生成器对话框 */}
                {showTableGenerator && (
                  <div className="bg-white border border-gray-200 rounded-md p-4 my-2 shadow-md">
                    <h4 className="font-medium text-gray-800 mb-3">创建表格</h4>
                    <div className="grid grid-cols-2 gap-4 mb-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">行数</label>
                        <input
                          type="number"
                          min="1"
                          max="10"
                          value={tableRows}
                          onChange={(e) => setTableRows(Math.min(10, Math.max(1, parseInt(e.target.value) || 1)))}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">列数</label>
                        <input
                          type="number"
                          min="1"
                          max="10"
                          value={tableCols}
                          onChange={(e) => setTableCols(Math.min(10, Math.max(1, parseInt(e.target.value) || 1)))}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                        />
                      </div>
                    </div>
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => setShowTableGenerator(false)}
                        className="mr-2 inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                      >
                        取消
                      </button>
                      <button
                        type="button"
                        onClick={generateTable}
                        className="inline-flex items-center px-3 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                      >
                        插入表格
                      </button>
                    </div>
                  </div>
                )}
                
                <textarea
                  id="markdown-editor"
                  ref={textareaRef}
                  className="w-full min-h-[400px] p-3 border rounded-md font-mono text-sm"
                  value={markdown}
                  onChange={(e) => {
                    // 保存历史记录
                    saveHistory(markdown);
                    setMarkdown(e.target.value);
                  }}
                  style={{ overflow: 'hidden', resize: 'none' }}
                />
              </div>
            </div>
            
            {/* 右侧预览区域 */}
            <div className="md:w-1/2 space-y-4">
              <div className="border border-gray-200 rounded-lg p-4 bg-white">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="text-lg font-medium flex items-center text-gray-800">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                    预览
                  </h3>
                  <button 
                    onClick={copyToClipboard}
                    className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm font-medium"
                  >
                    复制 HTML
                  </button>
                </div>
                <div 
                  ref={previewRef}
                  className="wechat-preview border border-gray-100 rounded-md p-4"
                >
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {markdown}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          </div>
          
          {/* 样式设置区域 */}
          <div className="border border-gray-200 rounded-lg p-4 bg-white">
            <h3 className="text-lg font-medium mb-3 flex items-center text-gray-800">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
              </svg>
              样式设置
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* 主题选择 */}
              <div>
                <label htmlFor="theme-select" className="block mb-2 font-medium text-gray-700">选择主题</label>
                <select 
                  id="theme-select"
                  className="w-full p-2 border rounded"
                  value={defaultThemes.findIndex(t => t.name === theme.name)}
                  onChange={(e) => setTheme(defaultThemes[parseInt(e.target.value)])}
                >
                  {defaultThemes.map((t, index) => (
                    <option key={t.name} value={index}>{t.name}</option>
                  ))}
                </select>
              </div>
              
              {/* 自定义CSS */}
              <div>
                <label htmlFor="custom-css" className="block mb-2 font-medium text-gray-700">自定义 CSS</label>
                <textarea
                  id="custom-css"
                  className="w-full h-24 p-2 border rounded font-mono text-sm"
                  value={customCSS}
                  onChange={(e) => setCustomCSS(e.target.value)}
                  placeholder=".wechat-preview p { font-size: 16px; }"
                />
              </div>
            </div>
          </div>
          
          {/* AI 样式生成部分 */}
          <div className="border border-gray-200 rounded-lg p-4 bg-white">
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-lg font-medium flex items-center text-gray-800">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                AI 样式生成
              </h3>
              <button
                type="button"
                onClick={toggleApiSettings}
                className="text-sm text-blue-600 hover:text-blue-800"
              >
                {showApiSettings ? '隐藏API设置' : '显示API设置'}
              </button>
            </div>
            
            {showApiSettings && (
              <div className="mb-4 p-4 bg-gray-50 rounded-md border border-gray-200">
                <ApiSettings 
                  showSettings={true}
                  toggleSettings={() => {}}
                  apiProvider={apiProvider}
                  setApiProvider={(provider) => {
                    setApiProvider(provider);
                    if (provider === 'openai') {
                      setApiUrl('https://api.openai.com/v1/chat/completions');
                      setModel('gpt-4');
                    } else if (provider === 'grok') {
                      setApiUrl('https://api.x.ai/v1/chat/completions');
                      setModel('grok-3-latest');
                    } else if (provider === 'ollama') {
                      setApiUrl('http://localhost:11434/api/generate');
                      setModel('llama2');
                      setApiKey('');
                    } else if (provider === 'deepseek') {
                      setApiUrl('https://api.deepseek.com/v1/chat/completions');
                      setModel('deepseek-chat');
                    } else if (provider === 'cherry') {
                      setApiUrl('http://localhost:23333/v1/chat/completions');
                      setModel('openai:gpt-4o-mini');
                    }
                    setStyleError(null);
                  }}
                  apiUrl={apiUrl}
                  setApiUrl={setApiUrl}
                  apiKey={apiKey}
                  setApiKey={setApiKey}
                  model={model}
                  setModel={setModel}
                  availableModels={availableModels}
                  fetchModels={fetchAvailableModels}
                />
              </div>
            )}
            
            <div>
              <label htmlFor="style-description" className="block text-sm font-medium mb-2 text-gray-700">
                描述您想要的样式 (例如: &ldquo;简约&rdquo;, &ldquo;科技感&rdquo;, &ldquo;清新自然&rdquo;)
              </label>
              <div className="flex">
                <input
                  id="style-description"
                  type="text"
                  className="flex-grow p-2 border rounded-l"
                  value={styleDescription}
                  onChange={(e) => setStyleDescription(e.target.value)}
                  placeholder="输入样式描述..."
                />
                <button
                  className="px-4 py-2 bg-blue-500 text-white rounded-r hover:bg-blue-600 disabled:bg-blue-300 flex items-center justify-center min-w-24"
                  onClick={generateAIStyle}
                  disabled={isGeneratingStyle || !styleDescription.trim()}
                >
                  {isGeneratingStyle ? (
                    <>
                      <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      生成中...
                    </>
                  ) : '生成样式'}
                </button>
              </div>
              {styleError && (
                <p className="text-red-500 text-sm mt-1">{styleError}</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
} 
