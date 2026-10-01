// frontend/src/components/ErrorState.tsx
interface ErrorProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorProps) {
  return (
    <div className="state state--error">
      <p>Ошибка: {message}</p>
      {onRetry && <button onClick={onRetry}>Повторить</button>}
    </div>
  );
}