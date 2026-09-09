import React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  className,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  type = 'button',
  disabled,
  ...props
}) => {
  const baseStyles =
    'inline-flex items-center justify-center font-semibold rounded-input transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-accent-focus focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none active:scale-[0.98]';

  const sizeStyles = {
    sm: 'min-h-9 px-3 py-1.5 text-xs gap-1.5',
    md: 'min-h-10 px-4 py-2 text-sm gap-2',
    lg: 'min-h-11 px-6 py-2.5 text-base gap-2.5',
  };

  const variantStyles = {
    primary: 'bg-gradient-to-r from-brand to-[#82ffe8] text-[#041312] hover:brightness-110 shadow-[0_0_28px_rgba(77,232,225,.18)] hover:shadow-[0_0_34px_rgba(77,232,225,.3)]',
    secondary: 'bg-surface-raised/80 border border-border text-text-primary hover:bg-surface hover:border-brand/40 hover:shadow-[0_0_24px_rgba(77,232,225,.07)]',
    danger: 'bg-status-error/10 border border-status-error/30 text-status-error hover:bg-status-error/20',
    ghost: 'text-text-secondary hover:text-text-primary hover:bg-surface-raised',
  };

  return (
    <button
      type={type}
      aria-busy={isLoading || undefined}
      className={twMerge(clsx(baseStyles, sizeStyles[size], variantStyles[variant], className))}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <svg
          className="animate-spin -ml-1 mr-2 h-4 w-4 text-current"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      ) : null}
      {children}
    </button>
  );
};
