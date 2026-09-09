export const ROUTES = {
  PUBLIC: {
    HOME: '/',
    TOOLS: '/tools',
    DOWNLOAD: '/download',
    HELP: '/help',
    SIGN_IN: '/sign-in',
  },
  APP: {
    OVERVIEW: '/app',
    PROJECTS: '/app/projects',
    PROJECT_EDITOR: (id: string = ':projectId') => `/app/projects/${id}/editor`,
    TOOLS: '/app/tools',
    TASKS: '/app/tasks',
    TASK_DETAIL: (id: string = ':jobId') => `/app/tasks/${id}`,
    DEVICES: '/app/devices',
    RESOURCES: '/app/resources',
    SETTINGS: '/app/settings',
    HELP: '/app/help',
  },
} as const;
