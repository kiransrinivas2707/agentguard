import { useEffect, useState } from "react";

function currentRoute(): string {
  const hash = window.location.hash.replace(/^#\/?/, "").trim();
  return hash || "inbox";
}

export function useHashRoute(): [string, (route: string) => void] {
  const [route, setRoute] = useState(currentRoute);

  useEffect(() => {
    const onChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const navigate = (next: string) => {
    if (currentRoute() === next) return;
    window.location.hash = `#/${next}`;
    setRoute(next);
  };

  return [route, navigate];
}
