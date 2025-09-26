import { WritingRequest, ApiResponse, PromptStyle, PolishRequest, PolishResponse } from './types';

// 流式生成回调函数类型
export type StreamCallback = (chunk: string, isComplete: boolean, error?: string) => void;

// 流式生成内容函数
export async function generateContentStream(
  request: WritingRequest, 
  onChunk: StreamCallback
): Promise<void> {
  try {
    const { promptStyle, topic, keywords, wordCount, llmApiUrl, llmApiKey, model, apiProvider, additionalHeaders } = request;

    // Format the prompt template
    const promptTemplate = formatPromptTemplate(promptStyle, topic, keywords, wordCount);

    const provider = apiProvider || '';

    // Detect API provider type from URL or provided value
    const isGrokApi = provider === 'grok' || llmApiUrl.includes('grok') || llmApiUrl.includes('xai');
    const isOllamaApi = provider === 'ollama' || llmApiUrl.includes('ollama') || llmApiUrl.includes('11434');
    const isDeepSeekApi = provider === 'deepseek' || llmApiUrl.includes('deepseek');
    const isGeminiVertexApi = provider === 'gemini-vertex' || llmApiUrl.includes('aiplatform.googleapis.com');

    if (isGeminiVertexApi) {
      onChunk('', false, 'Google Gemini (Vertex) 暂不支持流式输出，请关闭流式模式。');
      return;
    }

    // Prepare request body based on API provider
    let requestBody: Record<string, unknown>;
    let isOllama = false;
    
    if (isOllamaApi) {
      requestBody = {
        model: model || 'llama2',
        prompt: promptTemplate,
        stream: true
      };
      isOllama = true;
    } else if (isGrokApi) {
      requestBody = {
        messages: [{ role: 'user', content: promptTemplate }],
        model: "grok-3-latest",
        temperature: 0.7,
        stream: true
      };
    } else if (isDeepSeekApi) {
      requestBody = {
        model: model || 'deepseek-chat',
        messages: [{ role: 'user', content: promptTemplate }],
        temperature: 0.7,
        stream: true
      };
    } else {
      requestBody = {
        model: model || 'gpt-4',
        messages: [{ role: 'user', content: promptTemplate }],
        temperature: 0.7,
        stream: true
      };
    }
    
    const extraHeaders = additionalHeaders || {};

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...extraHeaders
    };

    if (!isOllamaApi && llmApiKey) {
      headers['Authorization'] = `Bearer ${llmApiKey}`;
    }

    console.log('开始流式请求到:', llmApiUrl);
    
    // 使用流式代理
    const response = await fetch('/api/stream-proxy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        targetUrl: llmApiUrl,
        headers,
        body: requestBody,
        isOllama
      })
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: { message: `流式请求失败: ${response.status}` } }));
      throw new Error(errorData.error?.message || `流式请求失败: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('无法读取流式响应');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine || !trimmedLine.startsWith('data: ')) continue;

          const dataStr = trimmedLine.slice(6);
          if (dataStr === '[DONE]') {
            onChunk('', true);
            return;
          }

          try {
            const data = JSON.parse(dataStr);
            
            if (data.error) {
              onChunk('', false, data.error.message);
              return;
            }

            if (data.choices && data.choices[0] && data.choices[0].delta) {
              const content = data.choices[0].delta.content || '';
              if (content) {
                onChunk(content, false);
              }
              
              if (data.choices[0].finish_reason === 'stop') {
                onChunk('', true);
                return;
              }
            }
          } catch (parseError) {
            console.warn('解析流式数据失败:', parseError);
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  } catch (error) {
    console.error('流式生成内容错误:', error);
    onChunk('', false, error instanceof Error ? error.message : '未知错误');
  }
}

export async function generateContent(request: WritingRequest): Promise<ApiResponse> {
  try {
    const { promptStyle, topic, keywords, wordCount, llmApiUrl, llmApiKey, model, apiProvider, additionalHeaders } = request;

    // Format the prompt template
    const promptTemplate = formatPromptTemplate(promptStyle, topic, keywords, wordCount);

    const provider = apiProvider || '';

    // Detect API provider type from URL (simple detection)
    const isGrokApi = provider === 'grok' || llmApiUrl.includes('grok') || llmApiUrl.includes('xai');
    const isOllamaApi = provider === 'ollama' || llmApiUrl.includes('ollama') || llmApiUrl.includes('11434');
    const isDeepSeekApi = provider === 'deepseek' || llmApiUrl.includes('deepseek');
    const isGeminiVertexApi = provider === 'gemini-vertex' || llmApiUrl.includes('aiplatform.googleapis.com');

    // URL 由前端组件和代理处理，这里直接使用
    const apiUrl = llmApiUrl;

    // Prepare request body based on API provider
    let requestBody: Record<string, unknown>;
    let isOllama = false;

    if (isOllamaApi) {
      // Ollama API format
      requestBody = {
        model: model || 'llama2',
        prompt: promptTemplate,
        stream: false
      };
      isOllama = true;
      console.log('使用 Ollama API 格式, 生成内容请求:', JSON.stringify(requestBody));
    } else if (isGrokApi) {
      // Grok API format
      requestBody = {
        messages: [
          {
            role: 'user',
            content: promptTemplate
          }
        ],
        model: "grok-3-latest",
        temperature: 0.7,
        stream: false
      };
    } else if (isDeepSeekApi) {
      // DeepSeek API format (与 OpenAI 兼容但有自己的模型名称)
      requestBody = {
        model: model || 'deepseek-chat',
        messages: [
          {
            role: 'user',
            content: promptTemplate
          }
        ],
        temperature: 0.7,
        stream: false
      };
    } else if (isGeminiVertexApi) {
      requestBody = {
        contents: [
          {
            role: 'user',
            parts: [
              {
                text: promptTemplate
              }
            ]
          }
        ],
        generationConfig: {
          temperature: 0.7
        }
      };
    } else {
      // OpenAI-compatible API format (default)
      requestBody = {
        model: model || 'gpt-4',
        messages: [
          {
            role: 'user',
            content: promptTemplate
          }
        ],
        temperature: 0.7
      };
    }
    
    // Prepare headers based on API provider
    const extraHeaders = additionalHeaders || {};

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...extraHeaders
    };

    // Add appropriate authorization header if not Ollama
    if (!isOllamaApi) {
      headers['Authorization'] = `Bearer ${llmApiKey}`;
    }

    console.log('准备发送请求到:', apiUrl);
    console.log('请求头:', JSON.stringify(headers, null, 2).replace(llmApiKey, '[REDACTED]'));
    console.log('请求体:', JSON.stringify(requestBody, null, 2));
    
    // 使用本地 API 代理来避免 CORS 问题
    try {
      // 尝试使用本地代理
      const proxyResponse = await fetch('/api/proxy', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          targetUrl: apiUrl,  // 使用可能修正后的 URL
          headers,
          body: requestBody,
          isOllama
        })
      });
      
      if (!proxyResponse.ok) {
        const errorData = await proxyResponse.json().catch(() => ({ error: { message: `代理服务错误: ${proxyResponse.status}` } }));
        throw new Error(errorData.error?.message || `代理服务错误: ${proxyResponse.status}: ${proxyResponse.statusText}`);
      }
      
      const data = await proxyResponse.json();
      console.log('API 响应:', data);
      
      // 保存原始响应用于调试
      console.log('原始 API 响应:', JSON.stringify(data, null, 2));
      
      // 以与测试页面相同的方式尝试不同方法提取内容
      let content = '';
      
      if (isGeminiVertexApi && Array.isArray(data.candidates) && data.candidates.length > 0) {
        const candidate = data.candidates[0];
        if (candidate?.content?.parts) {
          const parts = candidate.content.parts
            .map((part: { text?: string }) => part?.text || '')
            .filter((partText: string) => partText);
          content = parts.join('');
          console.log('从 Gemini Vertex candidates.content.parts 提取内容');
        } else if (typeof candidate?.content === 'string') {
          content = candidate.content;
          console.log('从 Gemini Vertex candidates.content 提取内容');
        } else if (candidate?.output) {
          const outputParts = Array.isArray(candidate.output)
            ? candidate.output
            : [candidate.output];
          content = outputParts.join('\n');
          console.log('从 Gemini Vertex candidates.output 提取内容');
        }
      } else if (data.choices && data.choices.length > 0 && data.choices[0].message && data.choices[0].message.content) {
        // 标准格式
        content = data.choices[0].message.content;
        console.log('从 choices[0].message.content 提取内容');
      } else if (data.message && data.message.content) {
        // 替代格式1
        content = data.message.content;
        console.log('从 message.content 提取内容');
      } else if (data.content) {
        // 替代格式2
        content = data.content;
        console.log('从 content 提取内容');
      } else if (data.output) {
        // 替代格式3
        content = data.output;
        console.log('从 output 提取内容');
      } else if (data.response) {
        // 替代格式4
        content = data.response;
        console.log('从 response 提取内容');
      } else if (data.text) {
        // 替代格式5
        content = data.text;
        console.log('从 text 提取内容');
      } else if (typeof data === 'string') {
        // 可能整个响应就是文本
        content = data;
        console.log('使用整个响应作为内容');
      } else if (data.error) {
        // 有明确的错误信息
        throw new Error(`API 错误: ${data.error.message || JSON.stringify(data.error)}`);
      } else {
        // 无法解析的响应
        throw new Error(`无法从API响应中提取内容: ${JSON.stringify(data)}`);
      }
      
      return { content };
    } catch (proxyError) {
      console.error('代理请求失败:', proxyError);
      throw proxyError;
    }
  } catch (error) {
    console.error('生成内容错误:', error);
    return {
      content: '',
      error: error instanceof Error ? error.message : '未知错误'
    };
  }
}

export function formatPromptTemplate(
  style: PromptStyle, 
  topic: string, 
  keywords: string[], 
  wordCount: number
): string {
  // Convert the style object to a formatted JSON string
  const styleJson = JSON.stringify(style, null, 4);
  
  // Format the keywords as a comma-separated list
  const keywordsStr = keywords.join('、');
  
  // Construct the complete prompt
  return `${styleJson}

---
遵循以上风格为我编写一篇${wordCount}字的文章，主题是${topic}，输出格式为markdown。
关键词：${keywordsStr}`;
}

export function exportToMarkdown(content: string): void {
  // Create a blob with the content
  const blob = new Blob([content], { type: 'text/markdown' });
  
  // Create a download link
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `writing_${new Date().toISOString().slice(0, 10)}.md`;
  
  // Trigger download
  document.body.appendChild(a);
  a.click();
  
  // Cleanup
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// 计算两段文本的差异并生成带有HTML标记的差异
function generateDiffMarkup(original: string, polished: string): string {
  const diffLines = [];
  const originalLines = original.split('\n');
  const polishedLines = polished.split('\n');
  
  // 非常简单的差异比较 - 行级别
  let i = 0, j = 0;
  
  while (i < originalLines.length || j < polishedLines.length) {
    const origLine = i < originalLines.length ? originalLines[i] : '';
    const polishLine = j < polishedLines.length ? polishedLines[j] : '';
    
    if (origLine === polishLine) {
      // 行相同，不做任何标记
      diffLines.push(origLine);
      i++;
      j++;
    } else {
      // 行不同，标记为已修改
      // 判断行是否被删除、添加或修改
      if (j + 1 < polishedLines.length && originalLines[i] === polishedLines[j + 1]) {
        // 添加行
        diffLines.push(`<ins class="diff-add">${polishLine}</ins>`);
        j++;
      } else if (i + 1 < originalLines.length && polishedLines[j] === originalLines[i + 1]) {
        // 删除行
        diffLines.push(`<del class="diff-del">${origLine}</del>`);
        i++;
      } else {
        // 修改行
        // 简单标记整行
        diffLines.push(`<del class="diff-del">${origLine}</del>`);
        diffLines.push(`<ins class="diff-add">${polishLine}</ins>`);
        i++;
        j++;
      }
    }
  }
  
  return diffLines.join('\n');
}

// 文章润色API
export async function polishContent(request: PolishRequest): Promise<PolishResponse> {
  try {
    const { originalText, llmApiUrl, llmApiKey, model, polishType } = request;
    
    // 生成润色提示词
    const promptTemplate = `请帮我润色以下文章，保持主要内容不变，但提升表达效果和语言流畅度。${polishType === 'academic' 
      ? '使用更加学术和专业的语言。' 
      : polishType === 'business' 
        ? '使用更加商业和专业的语言。' 
        : polishType === 'creative' 
          ? '使用更加生动和有创意的语言，增加趣味性和吸引力。' 
          : '使用更加流畅和自然的语言。'}
    
以下是原文：
${originalText}

请提供润色后的文本。只返回润色后的完整文本，不要添加任何说明或解释。`;

    // 确定API提供商类型
    const isGrokApi = llmApiUrl.includes('grok') || llmApiUrl.includes('xai');
    const isOllamaApi = llmApiUrl.includes('ollama') || llmApiUrl.includes('11434');
    const isDeepSeekApi = llmApiUrl.includes('deepseek');
    
    // URL 由前端组件和代理处理，这里直接使用
    const apiUrl = llmApiUrl;
    
    // 根据API提供商准备不同的请求格式
    let requestBody: Record<string, unknown>;
    let isOllama = false;
    
    if (isOllamaApi) {
      // Ollama API format
      requestBody = {
        model: model || 'llama2',
        prompt: promptTemplate,
        stream: false
      };
      isOllama = true;
      console.log('使用 Ollama API 格式, 润色请求:', JSON.stringify(requestBody));
    } else if (isGrokApi) {
      // Grok API format
      requestBody = {
        messages: [
          {
            role: 'user',
            content: promptTemplate
          }
        ],
        model: "grok-3-latest",
        temperature: 0.7,
        stream: false
      };
    } else if (isDeepSeekApi) {
      // DeepSeek API format (与 OpenAI 兼容但有自己的模型名称)
      requestBody = {
        model: model || 'deepseek-chat',
        messages: [
          {
            role: 'user',
            content: promptTemplate
          }
        ],
        temperature: 0.3,
        stream: false
      };
    } else {
      // OpenAI-compatible API format (default)
      requestBody = {
        model: model || 'gpt-4',
        messages: [
          {
            role: 'user',
            content: promptTemplate
          }
        ],
        temperature: 0.3,
        stream: false
      };
    }
    
    // 创建代理请求以避免CORS问题
    const proxyUrl = '/api/proxy';
    
    // 设置请求头
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    
    // 如果有API密钥且不是 Ollama，添加授权头
    if (llmApiKey && !isOllamaApi) {
      headers['Authorization'] = `Bearer ${llmApiKey}`;
    }
    
    console.log('润色请求目标:', apiUrl);
    console.log('请求头:', JSON.stringify(headers, null, 2).replace(llmApiKey || '', '[REDACTED]'));
    
    // 发送请求到代理
    try {
      const proxyResponse = await fetch(proxyUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          targetUrl: apiUrl,
          headers,
          body: requestBody,
          isOllama
        }),
      });
      
      if (!proxyResponse.ok) {
        const errorData = await proxyResponse.json();
        throw new Error(errorData.error?.message || `代理服务错误: ${proxyResponse.status}`);
      }
      
      const data = await proxyResponse.json();
      console.log('API 响应:', data);
      
      // 提取内容
      let polishedText = '';
      
      if (data.choices && data.choices.length > 0) {
        polishedText = data.choices[0].message.content;
      } else if (data.content) {
        polishedText = data.content;
      } else if (data.response) {
        polishedText = data.response;
      } else {
        throw new Error('无法从API响应中提取内容');
      }
      
      // 生成差异标记
      const diffMarkup = generateDiffMarkup(originalText, polishedText);
      
      return {
        originalText,
        polishedText,
        diffMarkup
      };
    } catch (proxyError) {
      console.error('代理请求失败:', proxyError);
      throw proxyError;
    }
  } catch (error) {
    console.error('润色请求失败:', error);
    return {
      originalText: request.originalText,
      polishedText: '',
      diffMarkup: '',
      error: error instanceof Error ? error.message : '未知错误'
    };
  }
} 