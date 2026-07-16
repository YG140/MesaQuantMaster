import type { ReactNode } from "react";

export function ErrorState({ message, children }: { message: string; children?: ReactNode }) {
  return (
    <div className="state error-state" role="alert">
      <p>{message}</p>
      {children}
    </div>
  );
}
