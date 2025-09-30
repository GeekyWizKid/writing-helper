"use client";

import React, { useState, useEffect } from 'react';
import { polishContent } from '../lib/api';
import { PolishRequest, PolishResponse } from '../lib/types';
import ApiSettings, { ApiProvider } from './ApiSettings';

export default function ArticlePolisher() {
  const [apiKey, setApiKey] = useState('');
  const [apiEndpoint, setApiEndpoint] = useState('https://api.openai.com/v1/chat/completions');
  const [apiProvider, setApiProvider] = useState<ApiProvider>('openai');
  const [isOllama, setIsOllama] = useState(false);
  const [ollamaEndpoint, setOllamaEndpoint] = useState('http://localhost:11434/api/generate');
  const [ollamaModel, setOllamaModel] = useState('llama2');
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [polishType, setPolishType] = useState<'standard' | 'academic' | 'business' | 'creative'>('standard');
  const [showApiSettings, setShowApiSettings] = useState(true);
  
  const [originalText, setOriginalText] = useState('');
  const [polishedResult, setPolishedResult] = useState<PolishResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // 获取可用的 Ollama 模型
  const fetchOllamaModels = async () => {
    try {
      setError(null); // 清除之前的错误
      console.log('开始获取 Ollama 模型列表...');
      
      // 使用代理接口而不是直接调用本地 Ollama API
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
          if (!modelsList.includes(ollamaModel)) {
            setOllamaModel(modelsList[0]);
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
      setError('无法获取 Ollama 模型列表，请确保 Ollama 服务正在运行');
      return []; // 返回空数组，避免后续处理出错
    }
  };

  // 获取 Cherry Server 模型列表
  const fetchCherryModels = async () => {
    try {
      setError(null);
      if (!apiKey) {
        setError('Cherry Server 需要 API 密钥以获取模型列表');
        return [] as string[];
      }
      const response = await fetch('/api/proxy/cherry-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          serverUrl: 'http://127.0.0.1:23333/v1/models',
          apiKey
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
        setAvailableModels(modelsList);
        if (!modelsList.includes(ollamaModel)) {
          // 这里沿用同一模型状态变量用于 UI 绑定
          setOllamaModel(modelsList[0]);
        }
      } else {
        setAvailableModels([]);
      }
      return modelsList;
    } catch (error) {
      console.error('获取 Cherry 模型列表失败:', error);
      setAvailableModels([]);
      setError('无法获取 Cherry Server 模型列表，请确保服务已启动并填入有效 API Key');
      return [] as string[];
    }
  };

  const fetchAvailableModels = async () => {
    if (apiProvider === 'ollama') return fetchOllamaModels();
    if (apiProvider === 'cherry') return fetchCherryModels();
    return [] as string[];
  };

  // 当选择 Ollama 时自动设置相关参数
  useEffect(() => {
    setIsOllama(apiProvider === 'ollama');
    if (apiProvider === 'ollama') {
      fetchOllamaModels();
    }
  }, [apiProvider]);

  const toggleApiSettings = () => {
    setShowApiSettings(!showApiSettings);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setPolishedResult(null);

    try {
      // 检查 API 密钥要求
      if (apiProvider !== 'ollama' && !apiKey) {
        // 非 Ollama 提供商需要 API 密钥
        throw new Error(`使用 ${apiProvider === 'openai' ? 'OpenAI' : apiProvider === 'grok' ? 'Grok' : apiProvider === 'deepseek' ? 'DeepSeek' : '自定义'} API 需要提供有效的 API 密钥`);
      }

      if (!originalText.trim()) {
        throw new Error('请输入需要润色的文章内容');
      }

      // 确保使用正确的 URL 端点
      let apiUrl = apiProvider === 'ollama' ? ollamaEndpoint : apiEndpoint;
      if (apiProvider === 'ollama' && !apiUrl.includes('/api/generate')) {
        const baseUrl = apiUrl.includes('/api/') 
          ? apiUrl.substring(0, apiUrl.indexOf('/api/')) 
          : apiUrl;
        apiUrl = `${baseUrl}/api/generate`;
        console.log('使用 Ollama 生成端点:', apiUrl);
      }

      // 根据API提供商选择不同的模型
      const model = apiProvider === 'ollama' ? ollamaModel : 
                    apiProvider === 'openai' ? 'gpt-4' : 
                    apiProvider === 'grok' ? 'grok-3-latest' : 
                    apiProvider === 'deepseek' ? 'deepseek-chat' : '';

      const request: PolishRequest = {
        originalText,
        llmApiUrl: apiUrl,
        llmApiKey: apiKey, // Ollama 不需要 API 密钥，但保留该字段以保持接口一致性
        model: model,
        polishType
      };

      const result = await polishContent(request);
      
      if (result.error) {
        throw new Error(result.error);
      }
      
      setPolishedResult(result);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '未知错误';
      setError(errorMessage);
      console.error('润色失败:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* 左侧设置区域 */}
        <div className="space-y-6">
          <div className="bg-white shadow-sm rounded-xl p-6 border border-gray-200">
            <h2 className="text-xl font-semibold mb-4 flex items-center text-gray-800">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
              </svg>
              润色设置
            </h2>
            
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* 使用抽离的 API 设置组件 */}
              <ApiSettings 
                showSettings={showApiSettings}
                toggleSettings={toggleApiSettings}
                apiProvider={apiProvider}
                setApiProvider={(provider) => {
                  setApiProvider(provider);
                  // 当更改提供商时，相应更新URL（使用预定义的默认值）
                  if (provider === 'openai') {
                    setApiEndpoint('https://api.openai.com/v1/chat/completions');
                  } else if (provider === 'grok') {
                    setApiEndpoint('https://api.grok.ai/v1/chat/completions');
                  } else if (provider === 'ollama') {
                    setOllamaEndpoint('http://localhost:11434/api/generate');  // 确保使用 /api/generate 端点
                  } else if (provider === 'deepseek') {
                    setApiEndpoint('https://api.deepseek.com/v1/chat/completions');
                  } else if (provider === 'cherry') {
                    setApiEndpoint('http://127.0.0.1:23333/v1/chat/completions');
                  }
                  // 自定义提供商不更改URL
                }}
                apiUrl={apiProvider === 'ollama' ? ollamaEndpoint : apiEndpoint}
                setApiUrl={(url) => {
                  if (apiProvider === 'ollama') {
                    setOllamaEndpoint(url);
                  } else {
                    setApiEndpoint(url);
                  }
                }}
                apiKey={apiKey}
                setApiKey={setApiKey}
                model={apiProvider === 'ollama' ? ollamaModel : apiProvider === 'openai' ? 'gpt-4' : apiProvider === 'grok' ? 'grok-3-latest' : apiProvider === 'deepseek' ? 'deepseek-chat' : apiProvider === 'cherry' ? 'openai:gpt-4o-mini' : ''}
                setModel={(model) => {
                  if (apiProvider === 'ollama') {
                    setOllamaModel(model);
                  } 
                  // 其他模型名称暂不需要保存
                }}
                availableModels={availableModels}
                fetchModels={fetchAvailableModels}
              />

              {/* 润色类型设置 */}
              <div className="bg-gray-50 p-5 rounded-lg border border-gray-200 space-y-4">
                <h3 className="font-medium text-gray-700 flex items-center">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" />
                  </svg>
                  润色类型
                </h3>
                
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex items-center">
                    <input
                      type="radio"
                      id="standard"
                      name="polishType"
                      checked={polishType === 'standard'}
                      onChange={() => setPolishType('standard')}
                      className="h-4 w-4 text-blue-600 border-gray-300"
                    />
                    <label htmlFor="standard" className="ml-2 text-sm text-gray-700">
                      标准润色
                    </label>
                  </div>
                  <div className="flex items-center">
                    <input
                      type="radio"
                      id="academic"
                      name="polishType"
                      checked={polishType === 'academic'}
                      onChange={() => setPolishType('academic')}
                      className="h-4 w-4 text-blue-600 border-gray-300"
                    />
                    <label htmlFor="academic" className="ml-2 text-sm text-gray-700">
                      学术润色
                    </label>
                  </div>
                  <div className="flex items-center">
                    <input
                      type="radio"
                      id="business"
                      name="polishType"
                      checked={polishType === 'business'}
                      onChange={() => setPolishType('business')}
                      className="h-4 w-4 text-blue-600 border-gray-300"
                    />
                    <label htmlFor="business" className="ml-2 text-sm text-gray-700">
                      商业润色
                    </label>
                  </div>
                  <div className="flex items-center">
                    <input
                      type="radio"
                      id="creative"
                      name="polishType"
                      checked={polishType === 'creative'}
                      onChange={() => setPolishType('creative')}
                      className="h-4 w-4 text-blue-600 border-gray-300"
                    />
                    <label htmlFor="creative" className="ml-2 text-sm text-gray-700">
                      创意润色
                    </label>
                  </div>
                </div>
              </div>
              
              <div className="flex space-x-4">
                <button
                  type="submit"
                  className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white py-2 px-6 rounded-md font-medium disabled:opacity-60 disabled:from-gray-400 disabled:to-gray-500 transition duration-150 ease-in-out transform hover:scale-105 shadow-md"
                  disabled={loading || (apiProvider !== 'ollama' && !apiKey)}
                >
                  {loading ? (
                    <span className="flex items-center">
                      <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      润色中...
                    </span>
                  ) : '开始润色'}
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* 右侧内容区域 */}
        <div>
          <div className="bg-white shadow-sm rounded-xl p-6 border border-gray-200 h-full flex flex-col">
            <h2 className="text-xl font-semibold text-gray-800 flex items-center mb-4">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
                <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
                <path fillRule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clipRule="evenodd" />
              </svg>
              原始文章
            </h2>
            <div className="mb-4 flex-grow">
              <textarea
                value={originalText}
                onChange={(e) => setOriginalText(e.target.value)}
                placeholder="请在此粘贴需要润色的文章..."
                className="w-full h-full p-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500 min-h-[200px] resize-none"
              />
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="mt-6 bg-red-50 text-red-700 p-4 rounded-md border border-red-200 mb-4">
          <div className="font-medium flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            错误: {error}
          </div>
        </div>
      )}

      {polishedResult && !error && (
        <div className="mt-8">
          <h2 className="text-xl font-semibold text-gray-800 mb-4">润色结果</h2>
          
          <div className="space-y-6">
            <div className="border border-gray-200 rounded-md overflow-hidden">
              <div className="bg-gray-50 px-4 py-2 border-b border-gray-200">
                <div className="flex justify-between items-center">
                  <h3 className="text-sm font-medium text-gray-700">标记修改</h3>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(polishedResult.polishedText);
                      alert('已复制到剪贴板');
                    }}
                    className="text-xs text-blue-600 hover:text-blue-800 flex items-center"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                    复制润色后文本
                  </button>
                </div>
              </div>
              <div className="p-4 bg-white">
                <div 
                  className="diff-container"
                  dangerouslySetInnerHTML={{ __html: polishedResult.diffMarkup }}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
} 
