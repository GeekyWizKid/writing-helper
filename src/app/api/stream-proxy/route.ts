import { NextRequest } from 'next/server';

export const maxDuration = 60;

// CORS helper
const getAllowedOrigin = (origin: string | null): string => {
  const allowedOrigins = process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:3000'];
  if (!origin || allowedOrigins.includes(origin)) {
    return origin || allowedOrigins[0];
  }
  return allowedOrigins[0];
};

export async function OPTIONS(request: NextRequest) {
  const origin = request.headers.get('origin');
  const allowedOrigin = getAllowedOrigin(origin);
  
  return new Response(null, {
    status: 200,
    headers: {
      'Access-Control-Allow-Origin': allowedOrigin,
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  });
}

export async function POST(request: NextRequest) {
  const origin = request.headers.get('origin');
  const allowedOrigin = getAllowedOrigin(origin);
  
  try {
    const { targetUrl, headers, body, isOllama } = await request.json();

    if (!targetUrl) {
      return new Response(
        JSON.stringify({ error: { message: '缺少目标 API URL' } }),
        { 
          status: 400,
          headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': allowedOrigin,
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          }
        }
      );
    }

    console.log('流式代理请求目标:', targetUrl);

    // 启用流式输出
    const streamBody = { ...body, stream: true };

    // 根据是否是 Ollama 请求调整请求体格式
    const requestBody = isOllama ? {
      model: body.model || 'llama2',
      prompt: Array.isArray(body.messages) ? body.messages[body.messages.length - 1].content : body.prompt,
      system: Array.isArray(body.messages) ? body.messages[0]?.content : undefined,
      stream: true
    } : streamBody;

    // 确保使用正确的 URL
    let requestUrl = targetUrl;
    if (isOllama && !targetUrl.includes('/api/generate')) {
      const baseUrl = targetUrl.includes('/api/') 
        ? targetUrl.substring(0, targetUrl.indexOf('/api/')) 
        : targetUrl;
      requestUrl = `${baseUrl}/api/generate`;
    }
    
    console.log('最终流式请求 URL:', requestUrl);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 600000); // 10分钟超时

    const fetchOptions: RequestInit = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(isOllama ? {} : headers),
      },
      body: JSON.stringify(requestBody),
      signal: controller.signal,
    };

    // 优先尝试原始 URL，如果失败且包含 localhost，则回退尝试 127.0.0.1 与 ::1
    let response: Response;
    try {
      response = await fetch(requestUrl, fetchOptions);
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : String(e);
      console.warn('初次流式 fetch 失败，准备回退:', errMsg);
      if (requestUrl.includes('localhost')) {
        const altIpv4 = requestUrl.replace('localhost', '127.0.0.1');
        try {
          console.log('尝试流式 IPv4 回退 URL:', altIpv4);
          response = await fetch(altIpv4, fetchOptions);
          requestUrl = altIpv4;
        } catch (e2) {
          const altIpv6 = requestUrl.replace('http://localhost', 'http://[::1]').replace('https://localhost', 'https://[::1]');
          console.log('尝试流式 IPv6 回退 URL:', altIpv6);
          response = await fetch(altIpv6, fetchOptions);
          requestUrl = altIpv6;
        }
      } else {
        throw e;
      }
    }

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorText = await response.text();
      console.error('流式API请求响应错误:', response.status, errorText);
      return new Response(
        JSON.stringify({ error: { message: `服务器返回错误：${response.status} ${errorText}` } }),
        { 
          status: response.status,
          headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': allowedOrigin,
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          }
        }
      );
    }

    // 创建流式响应
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        const reader = response.body?.getReader();
        if (!reader) {
          controller.close();
          return;
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
              if (!trimmedLine || trimmedLine === 'data: [DONE]') continue;

              if (isOllama) {
                // Ollama 流式响应处理
                try {
                  const ollamaData = JSON.parse(trimmedLine);
                  if (ollamaData.response) {
                    const chunk = {
                      id: `ollama-${Date.now()}`,
                      object: 'chat.completion.chunk',
                      created: Math.floor(Date.now() / 1000),
                      model: body.model || 'llama2',
                      choices: [{
                        index: 0,
                        delta: {
                          content: ollamaData.response
                        },
                        finish_reason: ollamaData.done ? 'stop' : null
                      }]
                    };
                    
                    controller.enqueue(encoder.encode(`data: ${JSON.stringify(chunk)}\n\n`));
                  }
                  
                  if (ollamaData.done) {
                    controller.enqueue(encoder.encode('data: [DONE]\n\n'));
                    break;
                  }
                } catch (e) {
                  console.warn('解析 Ollama 流式数据失败:', e);
                }
              } else {
                // OpenAI-compatible 流式响应处理
                if (trimmedLine.startsWith('data: ')) {
                  const dataStr = trimmedLine.slice(6);
                  if (dataStr === '[DONE]') {
                    controller.enqueue(encoder.encode('data: [DONE]\n\n'));
                    break;
                  }
                  
                  try {
                    const data = JSON.parse(dataStr);
                    controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
                  } catch (e) {
                    console.warn('解析流式数据失败:', e);
                  }
                } else if (trimmedLine) {
                  // 尝试直接解析为JSON
                  try {
                    const data = JSON.parse(trimmedLine);
                    controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
                  } catch (e) {
                    console.warn('解析JSON失败:', e);
                  }
                }
              }
            }
          }
        } catch (error) {
          console.error('流式处理错误:', error);
          const errorChunk = {
            error: { message: error instanceof Error ? error.message : '流式处理失败' }
          };
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(errorChunk)}\n\n`));
        } finally {
          controller.close();
        }
      },
    });

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': allowedOrigin,
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      },
    });
  } catch (error) {
    console.error('流式API代理错误:', error);
    
    return new Response(
      JSON.stringify({ error: { message: error instanceof Error ? error.message : '请求失败' } }),
      { 
        status: 500,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': allowedOrigin,
          'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        }
      }
    );
  }
}
