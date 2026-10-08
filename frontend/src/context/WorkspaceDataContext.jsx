import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { workspaceApi } from "@/lib/api";

const WorkspaceDataContext = createContext(null);

export const WorkspaceDataProvider = ({ children }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await workspaceApi.snapshot());
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || requestError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const value = useMemo(() => ({ data, loading, error, refresh }), [data, loading, error, refresh]);
  return <WorkspaceDataContext.Provider value={value}>{children}</WorkspaceDataContext.Provider>;
};

export const useWorkspaceData = () => {
  const context = useContext(WorkspaceDataContext);
  if (!context) throw new Error("useWorkspaceData requires WorkspaceDataProvider");
  return context;
};
