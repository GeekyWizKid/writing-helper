export interface PromptStyle {
  style_summary: string;
  language: {
    sentence_pattern: string[];
    word_choice: {
      formality_level: number;
      preferred_words: string[];
      avoided_words: string[];
    };
    rhetoric: string[];
  };
  structure: {
    paragraph_length: string;
    transition_style: string;
    hierarchy_pattern: string;
  };
  narrative: {
    perspective: string;
    time_sequence: string;
    narrator_attitude: string;
  };
  emotion: {
    intensity: number;
    expression_style: string;
    tone: string;
  };
  thinking: {
    logic_pattern: string;
    depth: number;
    rhythm: string;
  };
  uniqueness: {
    signature_phrases: string[];
    imagery_system: string[];
  };
  cultural: {
    allusions: string[];
    knowledge_domains: string[];
  };
  rhythm: {
    syllable_pattern: string;
    pause_pattern: string;
    tempo: string;
  };
}

export interface WritingRequest {
  promptStyle: PromptStyle;
  topic: string;
  keywords: string[];
  wordCount: number;
  llmApiUrl: string;
  llmApiKey: string;
  model: string;
  apiProvider?: string;
  additionalHeaders?: Record<string, string>;
}

export interface PolishRequest {
  originalText: string;
  llmApiUrl: string;
  llmApiKey: string;
  model: string;
  apiProvider?: string;
  additionalHeaders?: Record<string, string>;
  polishType?: 'standard' | 'academic' | 'business' | 'creative';
}

export interface PolishResponse {
  originalText: string;
  polishedText: string;
  diffMarkup: string;  // 包含标记的差异HTML
  error?: string;
}

export interface ApiResponse {
  content: string;
  error?: string;
} 