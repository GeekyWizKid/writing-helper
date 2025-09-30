"use client";

import React, { useState } from 'react';
import FeatureLayout from '../../components/FeatureLayout';
import ApiSettings, { ApiProvider } from '../../components/ApiSettings';
import { ApiResponse } from '../../../app/lib/types';

// 预设的洗稿 prompt
const presetPrompts = [
  {
    id: 'human-writing',
    name: '人类写作特征优化',
    description: '全面的人类写作特征优化方案，包含语言变化、思维过程、文化特征、修辞多样性、结构逻辑、情感语气等七大方面的优化策略',
    prompt: `请按照以下指导原则生成内容，以减少文本中的AI特征：

1. 语言变化与不规则性
   - 在句子长度上保持不规则变化，混合使用长句、短句和片段句
   - 偶尔使用不完全标准的表达方式，如口语化表达或省略句
   - 在段落长度上保持不规则性，避免过于均匀的段落结构

2. 思维过程与主观性
   - 展示思考的演进过程，包括初始想法、修正和反思
   - 加入个人观点和立场，使用"我认为"、"在我看来"等主观表达
   - 表达适当的不确定性，使用"可能"、"或许"、"我不确定，但..."等表达

3. 文化与时代特征
   - 融入当下特定的文化参考和时事引用
   - 使用特定群体或领域的习惯表达和术语
   - 适当使用新兴词汇或表达方式

4. 修辞与表达多样性
   - 使用多样化的修辞手法，如比喻、反问、夸张等
   - 在表达同一概念时使用不同的表述方式
   - 偶尔使用创新性表达或自创词汇

5. 结构与逻辑特征
   - 避免过于完美的结构和过于线性的逻辑展开
   - 偶尔进行话题跳转或思维跳跃，然后再回到主题
   - 在适当位置加入个人经历或案例作为支撑

6. 情感与语气变化
   - 在文本中展现情感波动和语气变化
   - 使用感叹、疑问等多样化的语气
   - 在正式与非正式语气之间适当切换

7. 特定领域处理
   - 如果是学术文本，融入学科特定的表达习惯和引用模式
   - 如果是新闻稿，模拟特定媒体的风格和报道角度
   - 如果是创意写作，展现个人化的写作风格和叙事技巧

请根据以上原则重写以下文本，确保文本既专业准确又具有自然的人类表达特征。仅输出正文，不要输出任何解释或说明。`
  },
  {
    id: 'ai-guide',
    name: 'AI修改指导',
    description: '分析文本内容，识别AI特征，生成个性化改写策略，提供具体示例，帮助减少AI痕迹，使文本更像人类撰写',
    prompt: `请分析以下内容，并生成一个去除AI特征的策略：

[用户输入的内容示例或描述]

请完成以下任务：
1. **识别风格特征**：分析文本的整体风格（如叙事性、描述性、技术性、对话性等）。
2. **检测AI特征**：找出文本中可能的AI生成特征（如过于正式、缺乏个性化、重复模式等）。
3. **生成改写策略**：提出具体的改写策略，帮助减少AI痕迹，包括但不限于：
   - 引入更多个人观点或情感表达
   - 增加或调整细节描述以增强真实性
   - 使用多样化的句式和词汇
   - 融入适当的幽默或文化背景
   - 调整文本结构以更接近人类写作习惯
4. **提供改写示例**：给出2-3个具体的改写示例，展示如何应用上述策略。

请确保生成的策略简洁明了，易于应用，并能有效减少AI检测率。`
  },
  {
    id: 'academic-paper',
    name: '学术论文人类化',
    description: '基于卡内基梅隆大学2025年AI文本检测报告的先进优化框架，全面提升学术论文的人类写作特征',
    prompt: `请根据以下学术文本人类化优化框架（2025增强版），对输入的论文文本进行重写，使其难以被AI检测工具识别：

## 一、认知节奏与思维破限

1. **认知节奏模拟**
   - 创造"冲刺-停顿-反思"的思维脉动：某些段落快速推进论点，某些段落放慢节奏深入探讨
   - 设计段落呼吸节律：故意变化段落长度（3-5句的短段落与10-15句的长段落交错）
   - 引入论证密度波动：在文本的25%处和75%处设置论证高密度区，其他区域适当放松
   - 安排"思维岔路与回归"：正式引入偏离主题的相关思考，然后通过过渡词（"回到刚才的问题"）返回主线

2. **思维链路破限**
   - 设置"认知中断点"：使用"这里我们需要暂停一下思考..."等表达，打断线性论证
   - 模拟直觉跳跃：省略某些逻辑步骤，使用"显然"、"不难看出"等表达（每2000字不超过3次）
   - 引入自我矛盾后调和：故意提出互相冲突的观点，然后通过更高层次思考进行整合
   - 融入反常规联想：建立远距离学科间的意外连接，例如"类似于文学中的意识流，量子力学也展现出..."

## 二、认知维度重构

1. **思维模式模拟**
   - 植入"假设-反驳-修正"论证链（每千字至少2.3个此类结构）
   - 增加反事实推理（counterfactual reasoning）段落，占比12%-15%
   - 引入跨学科隐喻系统，例如将量子纠缠概念迁移至社会学分析

2. **论证深度强化**
   - 构建三层论证结构：
     * 理论层：构建多变量方程和理论模型
     * 实证层：匹配3种或更多实证检验方法
     * 哲学层：嵌入认识论反思
   - 确保三维论证结构占比超过68%

## 三、语言特征优化矩阵

1. **词汇密度与变异**
   - 将名词占比提升至38.7%±1.2%（AI文本通常≤35%）
   - 文本特征丰富度指标(TF-IDF)需达到>0.85
   - 在同一语义场中使用不规则的词汇变异（如对同一概念使用3-4种不同表达）

2. **句法树深度与不规则性**
   - 从AI常见的平均3.2层提升至4-5层嵌套结构
   - 构造嵌套从句和复杂句法结构（CST≥4.7）
   - 有意打破句式平衡：在复杂句后跟随1-2个简短句，制造节奏变化

3. **语义网络**
   - 建立≥200节点的跨章节概念关联（AI文本通常<150）
   - 提高语义网络PageRank值>0.15
   - 设置概念"回环"：在文章后半部分重新引用前半部分的次要概念，形成认知闭环

4. **情感极性**
   - 打破中性区间集中的特征，引入学术激情标记
   - 使用"令人震惊的是"、"值得注意的是"等情感表达
   - 情感极性评分(VADER)需达到≥0.35
   - 设计情感波动：在高度客观的段落后安排带有轻微主观色彩的评论

## 四、动态调整机制

1. **批判性思维注入器**
   - 每300字插入1个质疑性设问（如"这一结论是否适用于X情境？"）
   - 在方法论章节添加2-3个替代方案比较框架
   - 结果讨论部分必须包含误差传播分析
   - 对自己的论点提出限制和约束条件（这是AI极少做的）

2. **个性化叙事模块**
   - 插入研究历程关键节点：
     * 初期探索阶段（注明耗时）
     * 方法迭代过程（提及版本号）
     * 关键突破时刻（引用具体会议或日期）
   - 个性化叙事元素密度约为0.15
   - 加入研究挫折描述："最初的实验结果令人失望，迫使我们重新思考..."

3. **跨学科整合引擎**
   - 每章引入1-2个异质学科概念（如用热力学第二定律解释文化传播）
   - 建立跨领域引文网络，非本学科文献占比≥25%
   - 创建"意外发现"叙事："在查阅X领域文献时，我们意外发现了与本研究相关的Y现象..."

## 五、学术规范增强

1. **引用动态校验**
   - 确保近五年高影响因子文献占比≥40%
   - 按学科分组引用，每个学科领域至少3篇高质量参考文献
   - 避免生成虚构参考文献（AI文本中30%为虚构引用）
   - 加入对引用文献的批判性评价："尽管Smith(2023)提出了引人注目的论点，但其方法存在明显局限..."

2. **方法论透明度**
   - 添加设备型号及参数波动范围（如"使用Thermo Fisher X系列，误差±0.05μm"）
   - 明确注明数据处理中的主观判断节点（如"异常值剔除标准设定为..."）
   - 坦诚研究局限："受设备精度所限，我们无法测量低于X的变化，这可能导致..."

## 六、优化效果评估

1. **检测抵抗指标**
   - 优化后文本应通过Turnitin AI检测（置信度<12%）
   - GPTZero "burstiness"评分应>85
   - 在GLTR检测中应呈现人类典型热力图分布

2. **学术价值指标**
   - 创新性密度：每千字含1.2个新概念/方法
   - 论证深度指数：跨三级学科引用≥5篇
   - 批判性强度：反驳段落占比≥18%

请对论文文本进行全面重写，保持原文的核心学术观点和发现，同时按照上述框架全面增强人类写作特征。特别注意：

1. 不要使文本过于完美和均衡
2. 有意识地在某些部分加入深入细节，而略过其他次要细节
3. 创造思维的自然起伏和流动
4. 打破预期的论证结构和推理链条
5. 在保持学术严谨的前提下，加入个性化、情感化元素

仅输出优化后的文本内容，不要包含对优化过程的说明。`
  },
  {
    id: 'hybrid-mode',
    name: '分析+改写混合模式',
    description: '先分析文本AI特征并生成针对性策略，再根据这些策略进行全文改写，提供更加个性化和有针对性的优化结果',
    prompt: `请执行以下两阶段处理，以优化文本并减少AI特征：

【第一阶段：分析与策略制定】
首先，请分析以下内容，并生成去除AI特征的策略：

===原文开始===
{text}
===原文结束===

请提供以下分析：
1. 文本整体风格特点概述
2. 识别出的主要AI特征（如句式规律、词汇选择模式、结构特点等）
3. 针对性的改写策略（至少5条具体的改进方向）

【第二阶段：全文改写】
现在，请根据上述制定的策略，对原文进行全面改写。改写时请注意：
- 保持原文的主要信息和观点
- 应用上述策略中提出的改进方向
- 增加语言的自然性和人类特征，包括：
  * 加入适当的主观表达和个人观点
  * 使用更多样化的句式和段落长度
  * 引入一些口语化或非正式表达
  * 适当增加情感色彩和语气变化
  * 打破过于规整的结构和逻辑展开

请直接输出改写后的文本，不需要包含分析过程或策略说明。`
  }
];

// 默认 API URLs
const API_URLS: Record<ApiProvider, string> = {
  openai: 'https://api.openai.com/v1/chat/completions',
  grok: 'https://api.x.ai/v1/chat/completions',
  ollama: 'http://localhost:11434/api/generate',
  deepseek: 'https://api.deepseek.com/v1/chat/completions',
  cherry: 'http://localhost:23333/v1/chat/completions',
  custom: ''
};

export default function AIRewritePage() {
  const [content, setContent] = useState('');
  const [result, setResult] = useState('');
  const [selectedPromptId, setSelectedPromptId] = useState('human-writing');
  const [customPrompt, setCustomPrompt] = useState('');
  const [useCustomPrompt, setUseCustomPrompt] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiResponseDetails, setApiResponseDetails] = useState<string | null>(null);
  const [useTwoStepMode, setUseTwoStepMode] = useState(false);
  const [processingStep, setProcessingStep] = useState<string | null>(null);

  // API 设置状态
  const [apiProvider, setApiProvider] = useState<ApiProvider>('openai');
  const [llmApiUrl, setLlmApiUrl] = useState<string>(API_URLS.openai);
  const [llmApiKey, setLlmApiKey] = useState<string>('');
  const [model, setModel] = useState<string>('gpt-4');
  const [showApiSettings, setShowApiSettings] = useState<boolean>(true);
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  // 获取当前选中的预设prompt文本
  const getSelectedPromptText = () => {
    if (useCustomPrompt) return customPrompt;
    const selected = presetPrompts.find(p => p.id === selectedPromptId);
    return selected ? selected.prompt : '';
  };

  // 获取 Ollama 模型列表
  const fetchOllamaModels = async () => {
    try {
      setError(null);

      const response = await fetch('/api/proxy/ollama-models', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ollamaUrl: 'http://localhost:11434/api/tags'
        }),
        signal: AbortSignal.timeout(5000)
      });

      if (!response.ok) {
        throw new Error(`无法获取模型列表: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();

      // 处理模型列表
      let modelsList: string[] = [];

      if (data.models && Array.isArray(data.models)) {
        modelsList = data.models.filter((model: unknown) => typeof model === 'string') as string[];
      } else if (data.names && Array.isArray(data.names)) {
        modelsList = data.names.filter((model: unknown) => typeof model === 'string') as string[];
      }

      if (modelsList.length > 0) {
        setAvailableModels(modelsList);

        // 如果当前模型不在列表中，则选择第一个模型
        if (!modelsList.includes(model)) {
          setModel(modelsList[0]);
        }
      } else {
        setAvailableModels([]);
      }

      return modelsList;
    } catch (error) {
      console.error('获取模型列表失败:', error);
      setAvailableModels([]);

      if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
        setError('无法连接到 Ollama 服务，请确保 Ollama 已安装并运行');
      } else if (error instanceof DOMException && error.name === 'AbortError') {
        setError('获取模型列表超时，请检查 Ollama 服务是否响应');
      } else {
        setError('无法获取 Ollama 模型列表，请确保 Ollama 服务正在运行');
      }

      return [];
    }
  };

  // 获取 Cherry Server 模型列表
  const fetchCherryModels = async () => {
    try {
      setError(null);
      if (!llmApiKey) {
        setError('Cherry Server 需要 API 密钥以获取模型列表');
        return [] as string[];
      }
      const response = await fetch('/api/proxy/cherry-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          serverUrl: 'http://localhost:23333/v1/models',
          apiKey: llmApiKey
        }),
        signal: AbortSignal.timeout(5000)
      });

      if (!response.ok) {
        throw new Error(`无法获取模型列表: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      let modelsList: string[] = [];
      if (data.models && Array.isArray(data.models)) {
        modelsList = data.models.filter((m: unknown) => typeof m === 'string') as string[];
      } else if (data && typeof data === 'object' && Array.isArray((data as { data?: unknown[] }).data)) {
        const list = ((data as { data?: unknown[] }).data || []) as unknown[];
        modelsList = list.map((item) => {
          const obj = item as Record<string, unknown>;
          return typeof obj?.id === 'string' ? (obj.id as string) : '';
        }).filter(Boolean);
      }

      if (modelsList.length > 0) {
        setAvailableModels(modelsList);
        if (!modelsList.includes(model)) {
          setModel(modelsList[0]);
        }
      } else {
        setAvailableModels([]);
      }
      return modelsList;
    } catch (error) {
      console.error('获取 Cherry 模型列表失败:', error);
      setAvailableModels([]);
      if (error instanceof DOMException && error.name === 'AbortError') {
        setError('获取模型列表超时，请检查 Cherry Server 是否响应');
      } else {
        setError('无法获取 Cherry Server 模型列表，请确保服务已启动并填入有效 API Key');
      }
      return [];
    }
  };

  const fetchAvailableModels = async () => {
    if (apiProvider === 'ollama') return fetchOllamaModels();
    if (apiProvider === 'cherry') return fetchCherryModels();
    return [] as string[];
  };

  // 处理API设置的显示/隐藏
  const toggleApiSettings = () => {
    setShowApiSettings(!showApiSettings);
  };

  // 直接从API获取内容
  const getContentFromApi = async (prompt: string, text: string): Promise<ApiResponse> => {
    try {
      // 检测API提供商类型
      const isGrokApi = llmApiUrl.includes('grok') || llmApiUrl.includes('xai');
      const isOllamaApi = llmApiUrl.includes('ollama') || llmApiUrl.includes('11434');
      const isDeepSeekApi = llmApiUrl.includes('deepseek');

      // 准备请求体
      let requestBody: Record<string, unknown>;
      let isOllama = false;

      const fullPrompt = prompt.includes('{text}') 
        ? prompt.replace('{text}', text)
        : `${prompt}\n\n原文：\n${text}`;

      if (isOllamaApi) {
        // Ollama API格式
        requestBody = {
          model: model || 'llama2',
          prompt: fullPrompt,
          stream: false
        };
        isOllama = true;
      } else if (isGrokApi) {
        // Grok API格式
        requestBody = {
          messages: [
            { role: 'user', content: fullPrompt }
          ],
          model: model || "grok-3-latest",
          temperature: 0.7,
          stream: false
        };
      } else if (isDeepSeekApi) {
        // DeepSeek API格式
        requestBody = {
          model: model || 'deepseek-chat',
          messages: [
            { role: 'user', content: fullPrompt }
          ],
          temperature: 0.7,
          stream: false
        };
      } else {
        // OpenAI兼容格式（默认）
        requestBody = {
          model: model || 'gpt-4',
          messages: [
            { role: 'user', content: fullPrompt }
          ],
          temperature: 0.7
        };
      }

      // 准备请求头
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };

      // 如果不是Ollama，添加授权头
      if (!isOllamaApi && llmApiKey) {
        headers['Authorization'] = `Bearer ${llmApiKey}`;
      }

      // 使用代理API避免CORS问题
      const proxyResponse = await fetch('/api/proxy', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          targetUrl: llmApiUrl,
          headers,
          body: requestBody,
          isOllama
        })
      });

      if (!proxyResponse.ok) {
        const errorData = await proxyResponse.json().catch(() => ({
          error: { message: `代理服务错误: ${proxyResponse.status}` }
        }));
        throw new Error(errorData.error?.message || `代理服务错误: ${proxyResponse.status}`);
      }

      const data = await proxyResponse.json();

      // 尝试不同方式提取内容
      let content = '';

      if (data.choices && data.choices.length > 0 && data.choices[0].message && data.choices[0].message.content) {
        content = data.choices[0].message.content;
      } else if (data.message && data.message.content) {
        content = data.message.content;
      } else if (data.content) {
        content = data.content;
      } else if (data.output) {
        content = data.output;
      } else if (data.response) {
        content = data.response;
      } else if (data.text) {
        content = data.text;
      } else if (typeof data === 'string') {
        content = data;
      } else if (data.error) {
        throw new Error(`API 错误: ${data.error.message || JSON.stringify(data.error)}`);
      } else {
        throw new Error(`无法从API响应中提取内容: ${JSON.stringify(data)}`);
      }

      return { content };
    } catch (error) {
      console.error('API请求错误:', error);
      return {
        content: '',
        error: error instanceof Error ? error.message : '未知错误'
      };
    }
  };

  // 处理提交
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!content.trim()) return;

    setLoading(true);
    setResult('');
    setError(null);
    setApiResponseDetails(null);

    try {
      // 检查 API 密钥
      if (apiProvider !== 'ollama' && !llmApiKey) {
        throw new Error(`使用 ${apiProvider === 'openai' ? 'OpenAI' : apiProvider === 'grok' ? 'Grok' : apiProvider === 'deepseek' ? 'DeepSeek' : '自定义'} API 需要提供有效的 API 密钥`);
      }

      // 获取所选提示词文本
      const promptText = getSelectedPromptText();
      
      // 如果启用了两步处理模式
      if (useTwoStepMode && selectedPromptId === 'human-writing') {
        // 第一步：使用AI修改指导获取策略
        setProcessingStep('正在分析文本并生成优化策略...');
        
        // 获取AI修改指导的prompt
        const aiGuidePrompt = presetPrompts.find(p => p.id === 'ai-guide')?.prompt || '';
        
        // 调用API获取修改策略
        const strategiesResponse = await getContentFromApi(aiGuidePrompt, content);
        
        if (strategiesResponse.error) {
          throw new Error(`生成策略失败: ${strategiesResponse.error}`);
        }
        
        // 第二步：使用生成的策略作为指导，应用人类写作特征优化
        setProcessingStep('正在根据策略优化文本...');
        
        // 构建新的prompt，结合策略和人类写作特征
        const humanWritingPrompt = presetPrompts.find(p => p.id === 'human-writing')?.prompt || '';
        
        const combinedPrompt = `
${humanWritingPrompt}

同时，请特别注意以下针对此文本的具体优化策略：

${strategiesResponse.content}

请根据以上策略和原则重写文本，确保文本既包含原文的核心信息，又具有自然的人类表达特征。仅输出优化后的文本，不要包含策略分析或说明。
        `.trim();
        
        // 使用组合prompt调用API
        const finalResponse = await getContentFromApi(combinedPrompt, content);
        
        if (finalResponse.error) {
          throw new Error(`文本优化失败: ${finalResponse.error}`);
        }
        
        setResult(finalResponse.content);
        
        // 记录策略详情以便查看
        setApiResponseDetails(`
【第一步：优化策略生成】
${strategiesResponse.content}

【第二步：根据策略进行优化】
已使用上述策略优化文本。
        `.trim());
      } else {
        // 常规处理 - 单步模式
        const response = await getContentFromApi(promptText, content);
        
        if (response.error) {
          setError(response.error);
          setApiResponseDetails('请查看浏览器控制台以获取更多错误详情。');
        } else if (!response.content || response.content.trim() === '') {
          setError('API 返回了空内容。这可能是由于 API 响应格式不符合预期。');
          setApiResponseDetails('请尝试切换 API 提供商或检查 API 密钥和 URL 是否正确。');
        } else {
          setResult(response.content);
        }
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '处理文本时发生未知错误';
      setError(errorMessage);

      // 添加更多帮助信息
      if (errorMessage.includes('Failed to fetch') || errorMessage.includes('网络')) {
        setApiResponseDetails('这可能是由于网络连接问题或 CORS 限制导致的。请确保您的网络连接稳定，并且 API 服务允许从您的网站发出请求。');
      } else if (errorMessage.includes('认证') || errorMessage.includes('授权') || errorMessage.includes('auth') || errorMessage.includes('key')) {
        setApiResponseDetails('这可能是由于 API 密钥不正确或已过期。请检查您的 API 密钥并确保它有效。');
      } else {
        setApiResponseDetails('请检查浏览器控制台以获取更多错误详情，或尝试使用不同的 API 提供商。');
      }
    } finally {
      setLoading(false);
      setProcessingStep(null);
    }
  };

  return (
    <FeatureLayout
      title="AI 文本优化器"
      subtitle="去除AI文本特征，使内容更自然、更人性化"
    >
      <div className="bg-white rounded-lg shadow-sm overflow-hidden">
        <div className="p-6">
          <div className="mb-6 bg-blue-50 text-blue-800 p-4 rounded-md border border-blue-200">
            <h3 className="text-lg font-medium mb-2 flex items-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>AI检测原理与对抗技术</span>
            </h3>
            <div className="text-sm space-y-2">
              <p>为了有效应对<strong>GPTZero</strong>等AI检测器，默认已选择&quot;人类写作特征优化&quot;预设，该预设专门针对AI检测器使用的统计学特征进行优化。</p>
              <p className="font-medium mt-2">主要对抗两项关键指标:</p>
              <ul className="list-disc pl-5 space-y-1">
                <li><strong>困惑度 (Perplexity)</strong>: 衡量文本的不可预测性。人类写作通常具有较高的困惑度，因为人类的词汇选择更具创造性和不可预测性。AI检测器会将低困惑度文本标记为AI生成。</li>
                <li><strong>突发性 (Burstiness)</strong>: 衡量句子长度和结构的变化程度。人类写作的句子长度变化更大，从极短句到复杂长句不等，而AI生成内容往往句子长度更为均匀。</li>
              </ul>
              <p className="mt-2">我们的优化技术基于最新研究，通过扰乱统计特征分布、打破句长模式、调整信息熵和模拟个性化语义嵌入等方法，帮助文本逃避检测，同时保持内容质量。</p>
            </div>
          </div>
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* API 设置部分 */}
            <ApiSettings
              showSettings={showApiSettings}
              toggleSettings={toggleApiSettings}
              apiProvider={apiProvider}
              setApiProvider={(provider) => {
                setApiProvider(provider);
                if (provider === 'openai') {
                  setLlmApiUrl('https://api.openai.com/v1/chat/completions');
                  setModel('gpt-4');
                } else if (provider === 'grok') {
                  setLlmApiUrl('https://api.x.ai/v1/chat/completions');
                  setModel('grok-3-latest');
                } else if (provider === 'ollama') {
                  setLlmApiUrl('http://localhost:11434/api/generate');
                  setModel('llama2');
                  setLlmApiKey('');
                } else if (provider === 'deepseek') {
                  setLlmApiUrl('https://api.deepseek.com/v1/chat/completions');
                  setModel('deepseek-chat');
                } else if (provider === 'cherry') {
                  setLlmApiUrl('http://localhost:23333/v1/chat/completions');
                  setModel('openai:gpt-4o-mini');
                }
                setError(null);
                setApiResponseDetails(null);
              }}
              apiUrl={llmApiUrl}
              setApiUrl={setLlmApiUrl}
              apiKey={llmApiKey}
              setApiKey={setLlmApiKey}
              model={model}
              setModel={setModel}
              availableModels={availableModels}
              fetchModels={fetchAvailableModels}
            />

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                输入需要处理的文本
              </label>
              <textarea
                rows={8}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="请粘贴需要去除AI特征的文本..."
                value={content}
                onChange={(e) => setContent(e.target.value)}
                required
              />
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-md font-medium text-gray-900">洗稿指令</h3>
                <div className="flex items-center space-x-4">
                  {selectedPromptId === 'human-writing' && (
                    <div className="flex items-center">
                      <input
                        type="checkbox"
                        id="useTwoStep"
                        checked={useTwoStepMode}
                        onChange={(e) => setUseTwoStepMode(e.target.checked)}
                        className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                      />
                      <label htmlFor="useTwoStep" className="ml-2 text-sm text-gray-600">
                        使用两步优化（先分析再优化）
                      </label>
                    </div>
                  )}
                  
                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      id="useCustom"
                      checked={useCustomPrompt}
                      onChange={(e) => {
                        setUseCustomPrompt(e.target.checked);
                        if (e.target.checked) {
                          setUseTwoStepMode(false);
                        }
                      }}
                      className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                    />
                    <label htmlFor="useCustom" className="ml-2 text-sm text-gray-600">
                      使用自定义指令
                    </label>
                  </div>
                </div>
              </div>

              {!useCustomPrompt ? (
                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-1">选择优化预设</label>
                  <div className="grid grid-cols-1 gap-2">
                    {presetPrompts.map((preset) => (
                      <div
                        key={preset.id}
                        className={`border rounded-md p-3 cursor-pointer transition-colors ${selectedPromptId === preset.id
                            ? 'bg-blue-50 border-blue-500'
                            : 'hover:bg-gray-50 border-gray-200'
                          }`}
                        onClick={() => {
                          setSelectedPromptId(preset.id);
                          if (preset.id !== 'human-writing') {
                            setUseTwoStepMode(false);
                          }
                        }}
                      >
                        <div className="font-medium">{preset.name}</div>
                        <div className="mt-2 text-xs text-gray-500">
                          {preset.description}
                        </div>
                      </div>
                    ))}
                  </div>
                  
                  {useTwoStepMode && (
                    <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                      <p className="text-xs text-yellow-800">
                        <strong>两步优化模式:</strong> 系统将先使用AI修改指导分析文本并生成个性化优化策略，然后根据这些策略使用人类写作特征优化模式改写文本。这种方式需要两次API调用，但能产生更有针对性的优化结果。
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    自定义指令
                  </label>
                  <textarea
                    rows={4}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                    placeholder="请输入自定义的洗稿指令..."
                    value={customPrompt}
                    onChange={(e) => setCustomPrompt(e.target.value)}
                    required={useCustomPrompt}
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    提示：优质的指令应明确说明如何改进文本、需要保留哪些内容以及需要什么风格。
                  </p>
                </div>
              )}
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={loading || !content.trim() || (useCustomPrompt && !customPrompt.trim()) || (apiProvider !== 'ollama' && !llmApiKey)}
                className={`px-4 py-2 rounded-md text-white font-medium ${loading || !content.trim() || (useCustomPrompt && !customPrompt.trim()) || (apiProvider !== 'ollama' && !llmApiKey)
                    ? 'bg-indigo-300 cursor-not-allowed'
                    : 'bg-indigo-600 hover:bg-indigo-700'
                  }`}
              >
                {loading ? (processingStep || '处理中...') : '优化文本'}
              </button>
            </div>
          </form>

          {error && (
            <div className="mt-4 bg-red-50 text-red-800 p-3 rounded-md border border-red-200">
              <p className="text-sm flex items-center">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>{error}</span>
              </p>
            </div>
          )}

          {result && (
            <div className="mt-6">
              <h3 className="text-lg font-medium mb-2">优化结果</h3>
              <div className="bg-gray-50 p-4 rounded-md border border-gray-200">
                <div className="whitespace-pre-wrap">{result}</div>
                <div className="mt-4 flex justify-end">
                  <button
                    type="button"
                    className="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                    onClick={() => {
                      navigator.clipboard.writeText(result);
                      alert('已复制到剪贴板');
                    }}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                    复制结果
                  </button>
                </div>
              </div>
              {apiResponseDetails && (
                <div className="mt-4">
                  <details className="text-sm text-gray-600">
                    <summary className="cursor-pointer hover:text-gray-900">{useTwoStepMode ? '查看优化策略和处理详情' : '查看技术细节'}</summary>
                    <div className="mt-2 p-3 bg-gray-50 rounded-md border border-gray-200 overflow-auto">
                      <pre className="text-xs whitespace-pre-wrap">{apiResponseDetails}</pre>
                    </div>
                  </details>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </FeatureLayout>
  );
} 
