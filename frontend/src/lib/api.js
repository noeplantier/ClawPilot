import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API });

api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem("openclaw_token");
  
  // --- AJOUT : Interception en mode Démo ---
  if (token === "bypass-token-12345") {
    // Annuler la requête pour ne pas déclencher d'erreur 404
    const source = axios.CancelToken.source();
    cfg.cancelToken = source.token;
    source.cancel('demo_mode');
  } else if (token) {
    cfg.headers.Authorization = `Bearer ${token}`;
  }
  // -----------------------------------------

  return cfg;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    // --- AJOUT : Fausse réponse en mode Démo ---
    if (axios.isCancel(err) && err.message === 'demo_mode') {
      // Renvoie un objet vide au lieu d'une erreur
      return Promise.resolve({ data: [] }); 
    }
    // -------------------------------------------

    if (err?.response?.status === 401) {
      localStorage.removeItem("openclaw_token");
      if (!window.location.pathname.startsWith("/login") && !window.location.pathname.startsWith("/register")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);