"use client";

import React, { useState, useEffect } from 'react';
import { SecureApiKeyManager } from '../lib/secureApiKey';

export type ApiProvider = 'openai' | 'grok' | 'ollama' | 'deepseek' | 'cherry' | 'custom';

// API 提供商帮助信息
const API_HELP: Record<ApiProvider, string> = {
  openai: '使用 OpenAI API，例如 GPT-4',
  grok: '使用 Grok API (X.AI)',
  ollama: '使用本地运行的 Ollama 服务',
  deepseek: '使用 DeepSeek API，例如 DeepSeek-V2',
  cherry: '使用 Cherry Studio Server（OpenAI 兼容）',
  custom: '配置自定义 API 端点'
};

// 默认 API URLs
const API_URLS: Record<ApiProvider, string> = {
  openai: 'https://api.openai.com/v1/chat/completions',
  grok: 'https://api.x.ai/v1/chat/completions',
  ollama: 'http://localhost:11434/api/generate',  // 确保使用 /api/generate 端点
  deepseek: 'https://api.deepseek.com/v1/chat/completions',
  cherry: 'http://localhost:23333/v1/chat/completions',
  custom: ''
};

export interface ApiSettingsProps {
  showSettings: boolean;
  toggleSettings: () => void;
  apiProvider: ApiProvider;
  setApiProvider: (provider: ApiProvider) => void;
  apiUrl: string;
  setApiUrl: (url: string) => void;
  apiKey: string;  // 注意：对于 Ollama，此值可以为空字符串
  setApiKey: (key: string) => void;
  model: string;
  setModel: (model: string) => void;
  // 仅在使用 Ollama 时需要
  availableModels?: string[];
  fetchModels?: () => Promise<string[] | void>;
}

export default function ApiSettings({
  showSettings,
  toggleSettings,
  apiProvider,
  setApiProvider,
  apiUrl,
  setApiUrl,
  apiKey,
  setApiKey,
  model,
  setModel,
  availableModels = [],
  fetchModels
}: ApiSettingsProps) {
  const [rememberMe, setRememberMe] = useState(false);
  const [showSecurityTip, setShowSecurityTip] = useState(false);
  
  // 组件加载时尝试恢复保存的 API Key
  useEffect(() => {
    const savedKey = SecureApiKeyManager.retrieve(apiProvider);
    if (savedKey && !apiKey) {
      setApiKey(savedKey);
      setRememberMe(true); // 如果有保存的key，说明之前选择了记住我
    }
  }, [apiProvider, apiKey, setApiKey]);

  // API Key 变化时自动保存（如果用户选择了记住我）
  useEffect(() => {
    if (apiKey && apiProvider !== 'ollama' && rememberMe) {
      SecureApiKeyManager.store(apiProvider, apiKey, rememberMe);
    }
  }, [apiKey, apiProvider, rememberMe]);
  
  const handleApiKeyChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newKey = e.target.value;
    setApiKey(newKey);
    
    // 如果选择了记住我，立即保存
    if (newKey && rememberMe && apiProvider !== 'ollama') {
      SecureApiKeyManager.store(apiProvider, newKey, rememberMe);
    }
  };

  const handleRememberMeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const remember = e.target.checked;
    setRememberMe(remember);
    
    if (apiKey && apiProvider !== 'ollama') {
      if (remember) {
        SecureApiKeyManager.store(apiProvider, apiKey, true);
      } else {
        SecureApiKeyManager.clear(apiProvider);
      }
    }
  };

  const clearStoredKey = () => {
    SecureApiKeyManager.clear(apiProvider);
    setApiKey('');
    setRememberMe(false);
  };
  
  const handleApiProviderChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const provider = e.target.value as ApiProvider;
    
    // 更新状态前先准备好新的 URL 和模型
    const newUrl = API_URLS[provider];
    
    // 先更新提供商
    setApiProvider(provider);
    
    // 设置默认 URL
    setApiUrl(newUrl);
    
    // 设置默认模型名称
    if (provider === 'openai') {
      setModel('gpt-4');
    } else if (provider === 'grok') {
      setModel('grok-3-latest');
    } else if (provider === 'ollama') {
      // 对于 Ollama，尝试获取可用模型
      setModel('llama2'); // 设置默认值，即使没有获取到模型列表也能有默认值
      if (fetchModels) {
        // 异步获取模型列表
        fetchModels().catch(err => {
          console.error('获取 Ollama 模型列表失败:', err);
          // 出错时不显示错误提示，仍保留默认值，避免干扰用户
          // 用户可以手动点击"刷新模型列表"按钮重试
        });
      }
    } else if (provider === 'deepseek') {
      setModel('deepseek-chat');
    } else if (provider === 'cherry') {
      // Cherry Server 兼容 OpenAI，模型名通常为 provider:model 形式
      setModel('openai:gpt-4o-mini');
      if (fetchModels) {
        fetchModels().catch(err => {
          console.error('获取 Cherry 模型列表失败:', err);
        });
      }
    }
    // 自定义提供商不设置默认模型
  };

  return (
    <div className="bg-gray-50 p-5 rounded-lg border border-gray-200 space-y-4">
      <div className="flex justify-between items-center cursor-pointer" onClick={toggleSettings}>
        <h3 className="font-medium text-gray-700 flex items-center">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm14 1H4v8a1 1 0 001 1h10a1 1 0 001-1V6zM4 4a1 1 0 011-1h10a1 1 0 011 1v1H4V4z" clipRule="evenodd" />
          </svg>
          API 设置
        </h3>
        <svg 
          xmlns="http://www.w3.org/2000/svg" 
          className={`h-5 w-5 text-gray-500 transition-transform duration-200 ${showSettings ? 'transform rotate-180' : ''}`} 
          viewBox="0 0 20 20" 
          fill="currentColor"
        >
          <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
        </svg>
      </div>

      {showSettings && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="apiProvider" className="block text-sm font-medium text-gray-700 mb-1">
              选择 API 提供商
            </label>
            <select
              id="apiProvider"
              value={apiProvider}
              onChange={handleApiProviderChange}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            >
              <option value="openai">OpenAI</option>
              <option value="grok">Grok (xAI)</option>
              <option value="ollama">Ollama (本地)</option>
              <option value="deepseek">DeepSeek</option>
              <option value="cherry">Cherry Studio Server</option>
              <option value="custom">自定义</option>
            </select>
            <p className="mt-1 text-xs text-gray-500">
              {API_HELP[apiProvider]}
            </p>
          </div>

          <div>
            <label htmlFor="apiUrl" className="block text-sm font-medium text-gray-700 mb-1">
              API 地址
            </label>
            <input
              type="text"
              id="apiUrl"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              placeholder="API 端点 URL"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label htmlFor="apiKey" className="block text-sm font-medium text-gray-700">
                API 密钥
              </label>
              <button
                type="button"
                onClick={() => setShowSecurityTip(!showSecurityTip)}
                className="text-xs text-blue-600 hover:text-blue-800 flex items-center"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
                安全提示
              </button>
            </div>
            
            {showSecurityTip && (
              <div className="mb-3 p-3 bg-blue-50 border border-blue-200 rounded-md text-xs text-blue-800">
                <div className="font-medium mb-1">🔒 API Key 安全提醒：</div>
                <ul className="space-y-1 text-blue-700">
                  <li>• API Key 仅在本地浏览器中临时存储</li>
                  <li>• 使用简单加密保护，避免明文存储</li>
                  <li>• 会话结束或过期后自动清除</li>
                  <li>• 请勿在公共设备上选择&quot;记住我&quot;</li>
                  <li>• 定期更换您的 API Key</li>
                </ul>
              </div>
            )}
            
            {apiProvider === 'ollama' ? (
              <div className="block w-full px-3 py-2 border border-gray-200 bg-gray-50 rounded-md text-gray-500 text-sm">
                <span className="flex items-center">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 text-green-500" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                  使用本地 Ollama 服务无需 API 密钥
                </span>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="relative">
                  <input
                    type="password"
                    id="apiKey"
                    value={apiKey}
                    onChange={handleApiKeyChange}
                    className="block w-full px-3 py-2 pr-10 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                    placeholder="输入您的 API 密钥"
                  />
                  {apiKey && (
                    <button
                      type="button"
                      onClick={clearStoredKey}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600"
                      title="清除保存的密钥"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  )}
                </div>
                
                <div className="flex items-center justify-between">
                  <label className="flex items-center text-xs text-gray-600">
                    <input
                      type="checkbox"
                      checked={rememberMe}
                      onChange={handleRememberMeChange}
                      className="mr-2 h-3 w-3 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    记住我 (7天)
                  </label>
                  
                  {SecureApiKeyManager.hasValidKey(apiProvider) && (
                    <span className="text-xs text-green-600 flex items-center">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      已保存
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>

          <div>
            <label htmlFor="model" className="block text-sm font-medium text-gray-700 mb-1">
              模型名称
            </label>
            {(apiProvider === 'ollama' || apiProvider === 'cherry') && availableModels && availableModels.length > 0 ? (
              <div className="space-y-2">
                <select
                  id="model"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                >
                  {availableModels.map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
                <div className="text-xs text-green-600">
                  已找到 {availableModels.length} 个可用模型
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <input
                  type="text"
                  id="model"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                  placeholder={(apiProvider === 'ollama' || apiProvider === 'cherry') ? '加载模型列表中或手动输入模型名称...' : '输入模型名称'}
                />
                {apiProvider === 'ollama' && (
                  <div className="text-xs text-gray-500">
                    {availableModels.length === 0 ? '未找到模型，请确保 Ollama 正在运行并已安装模型' : ''}
                  </div>
                )}
                {apiProvider === 'cherry' && (
                  <div className="text-xs text-gray-500">
                    提示: Cherry Server 的模型名通常为 provider:model，例如 openai:gpt-4o-mini。
                  </div>
                )}
              </div>
            )}
            {(apiProvider === 'ollama' || apiProvider === 'cherry') && fetchModels && (
              <button
                type="button"
                onClick={() => {
                  try {
                    console.log('开始获取 Ollama 模型列表...');
                    fetchModels()
                      .then((models) => {
                        console.log('获取 Ollama 模型成功，可用模型数量:', Array.isArray(models) ? models.length : availableModels.length);
                        // 强制刷新组件
                        if (availableModels.length > 0) {
                          const modelInput = document.getElementById('model');
                          if (modelInput) {
                            // 触发一个小动画以便用户知道列表已刷新
                            modelInput.classList.add('pulse-animation');
                            setTimeout(() => {
                              modelInput.classList.remove('pulse-animation');
                            }, 1000);
                          }
                        }
                      })
                      .catch(err => {
                        console.error('刷新模型列表失败:', err);
                      });
                  } catch (error) {
                    console.error('刷新模型列表失败:', error);
                  }
                }}
                className="mt-2 inline-flex items-center px-2.5 py-1.5 border border-transparent text-xs font-medium rounded text-blue-700 bg-blue-100 hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                刷新模型列表
              </button>
            )}
            {apiProvider === 'ollama' && (
              <div className="mt-2 text-xs text-gray-600">
                <p>
                  提示: 如需安装新模型，请在终端执行: <code className="px-1 py-0.5 bg-gray-100 rounded">ollama pull llama3.1</code>
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
} 
