// frontend/src/components/EmptyState.tsx
interface Props {
  message?: string;
}

export function EmptyState({ message = "Товары не найдены" }: Props) {
  return <div className="state state--empty">{message}</div>;
}