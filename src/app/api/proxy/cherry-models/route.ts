import { NextRequest, NextResponse } from 'next/server';

// 处理 OPTIONS 请求，支持 CORS
export async function OPTIONS() {
  return new NextResponse(null, {
    status: 200,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, x-api-key',
    },
  });
}

// 处理 POST 请求，获取 Cherry Server 模型列表
export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    const serverUrl = (body?.serverUrl as string) || 'http://localhost:23333/v1/models';
    const apiKey = (body?.apiKey as string) || '';

    if (!serverUrl || !serverUrl.startsWith('http')) {
      return NextResponse.json(
        { error: '无效的 Cherry Server URL' },
        { status: 400 }
      );
    }

    if (!apiKey) {
      return NextResponse.json(
        { error: '缺少 Cherry API Key' },
        { status: 401 }
      );
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(serverUrl, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Authorization': `Bearer ${apiKey}`,
          'x-api-key': apiKey,
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const text = await response.text();
        return NextResponse.json(
          { error: `Cherry Server 返回错误: ${response.status} ${text}` },
          { status: response.status }
        );
      }

      const data = await response.json();

      // 解析多种可能的数据结构，尽量提取模型 ID 列表
      const models: string[] = [];

      const pushId = (val: unknown) => {
        if (!val) return;
        if (typeof val === 'string') models.push(val);
      };

      const pushFromObj = (obj: Record<string, unknown>) => {
        // 可能的字段：id、model、name
        if (typeof obj.id === 'string') models.push(obj.id);
        else if (typeof obj.model === 'string') models.push(obj.model as string);
        else if (typeof obj.name === 'string') models.push(obj.name as string);
      };

      // 常见 OpenAI 兼容结构：{ data: [{ id: 'provider:model', ... }, ...] }
      if (data && typeof data === 'object' && Array.isArray((data as { data?: unknown[] }).data)) {
        const list = ((data as { data?: unknown[] }).data || []) as unknown[];
        for (const item of list) {
          if (typeof item === 'string') pushId(item);
          else if (item && typeof item === 'object') pushFromObj(item as Record<string, unknown>);
        }
      }

      // 备用：{ models: [...] }
      if (models.length === 0 && data && Array.isArray(data.models)) {
        for (const item of data.models) {
          if (typeof item === 'string') pushId(item);
          else if (item && typeof item === 'object') pushFromObj(item as Record<string, unknown>);
        }
      }

      // 备用：直接数组
      if (models.length === 0 && Array.isArray(data)) {
        for (const item of data) {
          if (typeof item === 'string') pushId(item);
          else if (item && typeof item === 'object') pushFromObj(item as Record<string, unknown>);
        }
      }

      // 去重
      const unique = Array.from(new Set(models)).filter(Boolean);

      return NextResponse.json({ models: unique });
    } catch (err: unknown) {
      const errObj = (err && typeof err === 'object') ? (err as Record<string, unknown>) : {};
      const name = (typeof errObj.name === 'string') ? errObj.name : '';
      const message = (typeof errObj.message === 'string') ? errObj.message : '未知错误';
      const isAbort = name === 'AbortError';
      return NextResponse.json(
        { error: `请求 Cherry Server 失败: ${isAbort ? '超时' : message}` },
        { status: isAbort ? 504 : 500 }
      );
    }
  } catch (error) {
    return NextResponse.json(
      { error: '请求格式错误' },
      { status: 400 }
    );
  }
}
