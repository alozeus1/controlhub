import { createContext, useContext, useState, useEffect } from "react";

const FeaturesContext = createContext(null);

const DEFAULT_FEATURES = {
  service_accounts: false,
  notifications: false,
  integrations: false,
  assets: false,
};

export function FeaturesProvider({ children }) {
  const [features, setFeatures] = useState(DEFAULT_FEATURES);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchFeatures = async () => {
      try {
        const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:9000";
        const res = await fetch(`${API_BASE}/features`);
        if (res.ok) {
          const data = await res.json();
          setFeatures(data);
        }
      } catch (err) {
        console.warn("Failed to fetch feature flags:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchFeatures();
  }, []);

  return (
    <FeaturesContext.Provider value={{ features, loading }}>
      {children}
    </FeaturesContext.Provider>
  );
}

export function useFeatures() {
  const context = useContext(FeaturesContext);
  if (!context) {
    throw new Error("useFeatures must be used within a FeaturesProvider");
  }
  return context;
}

export function useFeature(featureName) {
  const { features, loading } = useFeatures();
  return { enabled: features[featureName] || false, loading };
}
