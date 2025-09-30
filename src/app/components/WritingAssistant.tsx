"use client";

import React, { useState } from 'react';
import { PromptStyle, WritingRequest } from '../lib/types';
import { generateContent, generateContentStream, exportToMarkdown } from '../lib/api';
import PromptForm from './PromptForm';
import ApiSettings, { ApiProvider } from './ApiSettings';
import StreamingContent from './StreamingContent';

// Default prompt style template
const defaultPromptStyle: PromptStyle = {
  "style_summary": "质朴平实的散文笔触，以赶海为线索串联起乡愁记忆与人文关怀",
  "language": {
    "sentence_pattern": ["散文化的笔触，文字自然不造作", "营造场景叙事引人入胜"],
    "word_choice": {
      "formality_level": 3,
      "preferred_words": [ "家乡", "小时候"],
      "avoided_words": ["华丽辞藻", "生僻字"]
    },
    "rhetoric": ["回忆式叙述", "细节描写", "对比手法"]
  },
  "structure": {
    "paragraph_length": "中等偏长，200-300字",
    "transition_style": "以赶海的记忆和时光流逝进行过渡，今夕对比",
    "hierarchy_pattern": "以时空为经,以物为纬"
  },
  "narrative": {
    "perspective": "第一人称回忆视角",
    "time_sequence": "现在与过去交错",
    "narrator_attitude": "怀旧而理性"
  },
  "emotion": {
    "intensity": 3,
    "expression_style": "含蓄内敛",
    "tone": "温情怀旧"
  },
  "thinking": {
    "logic_pattern": "由物及事及情",
    "depth": 4,
    "rhythm": "舒缓平和"
  },
  "uniqueness": {
    "signature_phrases": ["我们那里", "小时候"],
    "imagery_system": ["赶海", "渔村", "童年"]
  },
  "cultural": {
    "allusions": ["典故适度", "穿插回忆"],
    "knowledge_domains": ["饮食文化", "赶海经历", "乡愁文学"]
  },
  "rhythm": {
    "syllable_pattern": "自然流畅",
    "pause_pattern": "长短句结合",
    "tempo": "从容不迫"
  }
};

// API 提供商选项
// type ApiProvider = 'openai' | 'grok' | 'ollama' | 'custom';

// 默认 API URLs
const API_URLS: Record<ApiProvider, string> = {
  openai: 'https://api.openai.com/v1/chat/completions',
  grok: 'https://api.grok.ai/v1/chat/completions',
  ollama: 'http://localhost:11434/api/generate',
  deepseek: 'https://api.deepseek.com/v1/chat/completions',
  cherry: 'http://127.0.0.1:23333/v1/chat/completions',
  custom: ''
};

export default function WritingAssistant() {
  const [promptStyle, setPromptStyle] = useState<PromptStyle>(defaultPromptStyle);
  const [topic, setTopic] = useState<string>('儿时赶海');
  const [keywords, setKeywords] = useState<string>('浙江海边、小时候、渔村、温暖、质朴');
  const [wordCount, setWordCount] = useState<number>(800);
  
  // API 设置
  const [apiProvider, setApiProvider] = useState<ApiProvider>('openai');
  const [llmApiUrl, setLlmApiUrl] = useState<string>(API_URLS.openai);
  const [llmApiKey, setLlmApiKey] = useState<string>('');
  const [model, setModel] = useState<string>('gpt-4'); // 添加模型设置
  
  const [output, setOutput] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [apiResponseDetails, setApiResponseDetails] = useState<string | null>(null);
  const [showPromptEditor, setShowPromptEditor] = useState<boolean>(false);
  const [showDebugInfo, setShowDebugInfo] = useState<boolean>(false);
  const [showApiSettings, setShowApiSettings] = useState<boolean>(true);
  
  // 流式输出相关状态
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [isComplete, setIsComplete] = useState<boolean>(true);
  const [useStreaming, setUseStreaming] = useState<boolean>(true); // 默认使用流式输出

  // 添加 Ollama 模型列表状态
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  // 获取可用的 Ollama 模型
  const fetchOllamaModels = async () => {
    try {
      setError(null); // 清除之前的错误
      console.log('开始获取 Ollama 模型列表...');
      
      // 使用代理接口而不是直接调用本地 Ollama API
      // 这可以避免浏览器的 CORS 限制
      const response = await fetch('/api/proxy/ollama-models', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ollamaUrl: 'http://localhost:11434/api/tags'
        }),
        // 添加超时设置以避免长时间等待
        signal: AbortSignal.timeout(5000)
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error(`获取模型列表失败: ${response.status} ${response.statusText}`, errorText);
        throw new Error(`无法获取模型列表: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log('获取到的 Ollama 模型数据:', data);
      
      // 检查数据格式，处理可能的不同结构
      let modelsList: string[] = [];
      
      if (data.models && Array.isArray(data.models)) {
        modelsList = data.models.filter((model: unknown) => typeof model === 'string') as string[];
      } else if (data.names && Array.isArray(data.names)) {
        modelsList = data.names.filter((model: unknown) => typeof model === 'string') as string[];
      }
      
      console.log('处理后的模型列表:', modelsList);
      
      if (modelsList.length > 0) {
        // 为了确保UI更新，先清空后设置
        setAvailableModels([]);
        setTimeout(() => {
          setAvailableModels(modelsList);
          
          // 如果当前模型不在列表中，则选择第一个模型
          if (!modelsList.includes(model)) {
            setModel(modelsList[0]);
          }
        }, 10);
        
        console.log(`成功获取到 ${modelsList.length} 个 Ollama 模型`);
      } else {
        console.warn('未找到 Ollama 模型列表');
        setAvailableModels([]);
        // 保持默认模型名称 'llama2'
      }
      
      return modelsList; // 返回处理后的模型列表
    } catch (error) {
      console.error('获取模型列表失败:', error);
      setAvailableModels([]); // 清空模型列表，使用默认值
      
      // 根据错误类型提供更具体的错误信息
      if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
        setError('无法连接到 Ollama 服务，请确保: 1) Ollama 已安装并运行 2) 服务地址正确');
      } else if (error instanceof DOMException && error.name === 'AbortError') {
        setError('获取模型列表超时，请检查 Ollama 服务是否响应');
      } else {
        setError('无法获取 Ollama 模型列表，请确保 Ollama 服务正在运行');
      }
      
      return []; // 返回空数组，避免后续处理出错
    }
  };

  // 获取可用的 Cherry Server 模型
  const fetchCherryModels = async () => {
    try {
      setError(null);
      if (!llmApiKey) {
        setError('Cherry Server 需要 API 密钥以获取模型列表');
        return [] as string[];
      }

      console.log('开始获取 Cherry Server 模型列表...');
      const response = await fetch('/api/proxy/cherry-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          serverUrl: 'http://127.0.0.1:23333/v1/models',
          apiKey: llmApiKey
        }),
        signal: AbortSignal.timeout(5000)
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`获取 Cherry 模型列表失败: ${response.status} ${response.statusText}`, errorText);
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
        setAvailableModels([]);
        setTimeout(() => {
          setAvailableModels(modelsList);
          if (!modelsList.includes(model)) {
            setModel(modelsList[0]);
          }
        }, 10);
        console.log(`成功获取到 ${modelsList.length} 个 Cherry 模型`);
      } else {
        console.warn('未找到 Cherry 模型列表');
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

  const handleKeywordsChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setKeywords(e.target.value);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setApiResponseDetails(null);
    setOutput('');
    setIsStreaming(useStreaming);
    setIsComplete(false);

    try {
      // 检查 API 密钥
      if (apiProvider !== 'ollama' && !llmApiKey) {
        throw new Error(`使用 ${apiProvider === 'openai' ? 'OpenAI' : apiProvider === 'grok' ? 'Grok' : apiProvider === 'deepseek' ? 'DeepSeek' : '自定义'} API 需要提供有效的 API 密钥`);
      }
      
      // 确保使用正确的 URL 端点
      let apiUrl = llmApiUrl;
      if (apiProvider === 'ollama' && !llmApiUrl.includes('/api/generate')) {
        const baseUrl = llmApiUrl.includes('/api/') 
          ? llmApiUrl.substring(0, llmApiUrl.indexOf('/api/')) 
          : llmApiUrl;
        apiUrl = `${baseUrl}/api/generate`;
        console.log('使用 Ollama 生成端点:', apiUrl);
      }

      // Prepare the request
      const request: WritingRequest = {
        promptStyle,
        topic,
        keywords: keywords.split('、'),
        wordCount,
        llmApiUrl: apiUrl,
        llmApiKey,
        model
      };

      console.log(`开始请求 ${apiProvider} API，使用模型: ${model}，流式模式: ${useStreaming}`);
      
      if (useStreaming) {
        // 使用流式输出
        await generateContentStream(request, (chunk, isCompleteChunk, errorMsg) => {
          if (errorMsg) {
            setError(errorMsg);
            setApiResponseDetails('请查看浏览器控制台以获取更多错误详情。');
            setIsStreaming(false);
            setIsComplete(true);
          } else if (isCompleteChunk) {
            setIsStreaming(false);
            setIsComplete(true);
            console.log('流式生成完成');
          } else if (chunk) {
            setOutput(prev => prev + chunk);
          }
        });
      } else {
        // 使用传统的一次性生成
        const response = await generateContent(request);
        
        if (response.error) {
          setError(response.error);
          setApiResponseDetails('请查看浏览器控制台以获取更多错误详情。');
        } else if (!response.content || response.content.trim() === '') {
          setError('API 返回了空内容。这可能是由于 API 响应格式不符合预期。');
          setApiResponseDetails('请尝试切换 API 提供商或检查 API 密钥和 URL 是否正确。');
        } else {
          setOutput(response.content);
          setIsComplete(true);
        }
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '生成内容时发生未知错误';
      setError(errorMessage);
      setIsStreaming(false);
      setIsComplete(true);
      
      // 添加更多帮助信息
      if (errorMessage.includes('Failed to fetch') || errorMessage.includes('网络')) {
        setApiResponseDetails('这可能是由于网络连接问题或 CORS 限制导致的。请确保您的网络连接稳定，并且 API 服务允许从您的网站发出请求。');
      } else if (errorMessage.includes('认证') || errorMessage.includes('授权') || errorMessage.includes('auth') || errorMessage.includes('key')) {
        setApiResponseDetails('这可能是由于 API 密钥不正确或已过期。请检查您的 API 密钥并确保它有效。');
      } else {
        setApiResponseDetails('请检查浏览器控制台以获取更多错误详情，或尝试使用不同的 API 提供商。');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleExport = () => {
    if (output) {
      exportToMarkdown(output);
    }
  };

  const toggleDebugInfo = () => {
    setShowDebugInfo(!showDebugInfo);
  };

  const toggleApiSettings = () => {
    setShowApiSettings(!showApiSettings);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold text-gray-800 mb-2">AI 写作助手</h1>
          <p className="text-gray-600 max-w-2xl mx-auto">使用先进的人工智能模型，根据您的风格偏好生成高质量文章</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Input Section */}
          <div className="space-y-6">
            <div className="bg-white shadow-sm rounded-xl p-6 border border-gray-200">
              <h2 className="text-xl font-semibold mb-4 flex items-center text-gray-800">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
                </svg>
                写作设置
              </h2>
              
              <form onSubmit={handleSubmit} className="space-y-6">
                {/* LLM API Settings */}
                <div className="bg-gray-50 p-5 rounded-lg border border-gray-200 space-y-4">
                  <div className="flex justify-between items-center cursor-pointer" onClick={toggleApiSettings}>
                    <h3 className="font-medium text-gray-700 flex items-center">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm14 1H4v8a1 1 0 001 1h10a1 1 0 001-1V6zM4 4a1 1 0 011-1h10a1 1 0 011 1v1H4V4z" clipRule="evenodd" />
                      </svg>
                      API 设置
                    </h3>
                    <div className="flex items-center space-x-2">
                      <button
                        type="button"
                        className="text-xs bg-gray-200 hover:bg-gray-300 text-gray-700 px-2 py-1 rounded-md transition duration-150 ease-in-out"
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleDebugInfo();
                        }}
                      >
                        {showDebugInfo ? '隐藏调试信息' : '显示调试信息'}
                      </button>
                      <svg 
                        xmlns="http://www.w3.org/2000/svg" 
                        className={`h-5 w-5 text-gray-500 transition-transform duration-200 ${showApiSettings ? 'transform rotate-180' : ''}`} 
                        viewBox="0 0 20 20" 
                        fill="currentColor"
                      >
                        <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                      </svg>
                    </div>
                  </div>

                  {showApiSettings && (
                    <ApiSettings 
                      showSettings={true}
                      toggleSettings={() => {}} // 这里已经控制显示了，所以传入空函数
                      apiProvider={apiProvider}
                      setApiProvider={(provider) => {
                        setApiProvider(provider);
                        // 当更改提供商时，直接更新URL（使用预定义的默认值）
                        if (provider === 'openai') {
                          setLlmApiUrl('https://api.openai.com/v1/chat/completions');
                          setModel('gpt-4');
                        } else if (provider === 'grok') {
                          setLlmApiUrl('https://api.grok.ai/v1/chat/completions');
                          setModel('grok-3-latest');
                        } else if (provider === 'ollama') {
                          setLlmApiUrl('http://localhost:11434/api/generate');  // 确保使用 /api/generate 端点
                          setModel('llama2');
                          // 清空 API Key，因为 Ollama 不需要
                          setLlmApiKey('');
                        } else if (provider === 'deepseek') {
                          setLlmApiUrl('https://api.deepseek.com/v1/chat/completions');
                          setModel('deepseek-chat');
                        } else if (provider === 'cherry') {
                          setLlmApiUrl('http://127.0.0.1:23333/v1/chat/completions');
                          setModel('openai:gpt-4o-mini');
                        }
                        // 重置错误
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
                  )}
                </div>

                {/* Content Settings */}
                <div className="bg-gray-50 p-5 rounded-lg border border-gray-200 space-y-4">
                  <h3 className="font-medium text-gray-700 flex items-center">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" />
                    </svg>
                    内容设置
                  </h3>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      主题
                    </label>
                    <input
                      type="text"
                      className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                      value={topic}
                      onChange={(e) => setTopic(e.target.value)}
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      关键词（用、分隔）
                    </label>
                    <input
                      type="text"
                      className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                      value={keywords}
                      onChange={handleKeywordsChange}
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      字数
                    </label>
                    <input
                      type="number"
                      min="100"
                      step="100"
                      className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                      value={wordCount}
                      onChange={(e) => setWordCount(Number(e.target.value))}
                      required
                    />
                  </div>
                </div>
                
                {/* Prompt Style Editor */}
                <div 
                  className="bg-gray-50 p-5 rounded-lg border border-gray-200 space-y-4"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="flex justify-between items-center">
                    <h3 className="font-medium text-gray-700 flex items-center">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
                        <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
                        <path fillRule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clipRule="evenodd" />
                      </svg>
                      提示词风格
                    </h3>
                    <button
                      type="button"
                      className="text-blue-600 hover:text-blue-800 text-sm font-medium transition duration-150 ease-in-out"
                      onClick={(e) => {
                        e.preventDefault(); // 阻止可能的表单提交
                        e.stopPropagation(); // 阻止事件冒泡
                        setShowPromptEditor(!showPromptEditor);
                      }}
                    >
                      {showPromptEditor ? '收起编辑器' : '展开编辑器'}
                    </button>
                  </div>

                  {showPromptEditor && (
                    <div onClick={(e) => e.stopPropagation()}>
                      <PromptForm 
                        initialStyle={promptStyle} 
                        onStyleChange={setPromptStyle} 
                      />
                    </div>
                  )}
                </div>
                
                <div className="flex space-x-4">
                  <button
                    type="submit"
                    className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white py-2 px-6 rounded-md font-medium disabled:opacity-60 disabled:from-gray-400 disabled:to-gray-500 transition duration-150 ease-in-out transform hover:scale-105 shadow-md"
                    disabled={isLoading || (apiProvider !== 'ollama' && !llmApiKey)}
                  >
                    {isLoading ? (
                      <span className="flex items-center">
                        <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        生成中...
                      </span>
                    ) : '生成内容'}
                  </button>
                  <a
                    href="/grok"
                    className="bg-transparent border border-gray-300 text-gray-700 hover:bg-gray-100 py-2 px-4 rounded-md font-medium transition duration-150 ease-in-out flex items-center"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2h-1V9z" clipRule="evenodd" />
                    </svg>
                    API 测试页面
                  </a>
                </div>
              </form>
            </div>
          </div>
        
          {/* Output Section */}
          <div>
            <div className="bg-white shadow-sm rounded-xl p-6 border border-gray-200 h-full flex flex-col">
              <div className="flex justify-between items-center mb-4">
                <div className="flex items-center">
                  <h2 className="text-xl font-semibold text-gray-800 flex items-center">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    生成结果
                  </h2>
                  
                  {/* 流式模式切换 */}
                  <div className="ml-6 flex items-center">
                    <label className="flex items-center text-sm text-gray-600 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={useStreaming}
                        onChange={(e) => setUseStreaming(e.target.checked)}
                        className="mr-2 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                        disabled={isLoading}
                      />
                      <span className="flex items-center">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        流式输出
                      </span>
                    </label>
                  </div>
                </div>
                
                {output && isComplete && (
                  <button
                    onClick={handleExport}
                    className="bg-green-600 hover:bg-green-700 text-white py-1.5 px-4 rounded-md text-sm flex items-center transition duration-150 ease-in-out shadow-sm"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                    导出 Markdown
                  </button>
                )}
              </div>
              
              <div className="flex-grow">
                <StreamingContent
                  content={output}
                  isStreaming={isStreaming && isLoading}
                  isComplete={isComplete}
                  error={error || undefined}
                  className="h-full"
                />
                
                {error && apiResponseDetails && (
                  <div className="mt-4 bg-yellow-50 text-yellow-800 p-3 rounded-md border border-yellow-200 text-sm">
                    <div className="font-medium mb-1">建议:</div>
                    {apiResponseDetails}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
} 
