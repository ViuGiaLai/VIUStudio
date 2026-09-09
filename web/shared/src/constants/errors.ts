/**
 * Error content and actions strictly defined in VIUStudio Web specification Section 18
 */
export interface ErrorDefinition {
  code: string;
  message: string;
  actionText: string;
  actionType: 'connect' | 'help' | 'download_model' | 'details' | 'relink' | 'cancel' | 'review' | 'export_again' | 'storage' | 'retry';
}

export const ERROR_DEFINITIONS: Record<string, ErrorDefinition> = {
  NOT_CONNECTED: {
    code: 'NOT_CONNECTED',
    message: 'Connect your computer to process media.',
    actionText: 'Connect device',
    actionType: 'connect',
  },
  DEVICE_OFFLINE: {
    code: 'DEVICE_OFFLINE',
    message: 'My PC is offline. Last seen 5 minutes ago.',
    actionText: 'Connection help',
    actionType: 'help',
  },
  MISSING_MODEL: {
    code: 'MISSING_MODEL',
    message: 'This voice needs a model download.',
    actionText: 'Download model',
    actionType: 'download_model',
  },
  INDETERMINATE_PROGRESS: {
    code: 'INDETERMINATE_PROGRESS',
    message: 'Loading speech model…',
    actionText: 'Details',
    actionType: 'details',
  },
  FILE_MISSING: {
    code: 'FILE_MISSING',
    message: 'Source file could not be found on this device.',
    actionText: 'Relink media',
    actionType: 'relink',
  },
  JOB_NOT_ACCEPTED: {
    code: 'JOB_NOT_ACCEPTED',
    message: 'Waiting for your device to accept this task.',
    actionText: 'Cancel',
    actionType: 'cancel',
  },
  REVISION_CONFLICT: {
    code: 'REVISION_CONFLICT',
    message: 'This project changed on another session.',
    actionText: 'Review changes',
    actionType: 'review',
  },
  OUTDATED_OUTPUT: {
    code: 'OUTDATED_OUTPUT',
    message: 'This output was created from an earlier revision.',
    actionText: 'Export again',
    actionType: 'export_again',
  },
  INSUFFICIENT_DISK: {
    code: 'INSUFFICIENT_DISK',
    message: 'Not enough free space for this task.',
    actionText: 'Manage storage',
    actionType: 'storage',
  },
  TASK_FAILED: {
    code: 'TASK_FAILED',
    message: 'Task failed during processing.',
    actionText: 'Retry failed cues',
    actionType: 'retry',
  },
  LOCAL_ACCESS_BLOCKED: {
    code: 'LOCAL_ACCESS_BLOCKED',
    message: 'Allow local connection to preview files on this computer.',
    actionText: 'Connection help',
    actionType: 'help',
  },
};
