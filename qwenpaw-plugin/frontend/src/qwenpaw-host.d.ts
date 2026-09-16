import type React from "react";

declare global {
  interface Window {
    QwenPaw: {
      host: {
        React: typeof React;
        antd: any;
        antdIcons?: any;
        useLocale?: () => string;
        getApiUrl: (path: string) => string;
        getApiToken: () => string;
      };
      memoryBackends: {
        register(
          pluginId: string,
          extension: Record<string, unknown>,
        ): { dispose(): void };
      };
    };
  }
}

export {};
