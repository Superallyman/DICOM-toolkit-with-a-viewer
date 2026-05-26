// src/utils/axiosInstance.ts
import axios, {
  AxiosError,
  AxiosHeaders,
  InternalAxiosRequestConfig,
} from "axios";
import { loaderBus } from "./loaderBus";
import { API_URL } from "./env";

const api = axios.create({
  baseURL: API_URL,
});

// ---- SSR-safe token helpers
const getAccessToken = () =>
  typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

const getRefreshToken = () =>
  typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;

// REQUEST: add bearer token + toggle global loader (unless X-Skip-Loader set)
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Normalize headers to AxiosHeaders instance
    config.headers = AxiosHeaders.from(config.headers || {});

    const token = getAccessToken();
    if (token) {
      (config.headers as AxiosHeaders).set("Authorization", `Bearer ${token}`);
    }

    const skip = (config.headers as AxiosHeaders).get("X-Skip-Loader");
    if (!skip) loaderBus.inc();

    return config;
  },
  (error: AxiosError) => {
    loaderBus.dec();
    return Promise.reject(error);
  }
);

// RESPONSE: turn off loader; refresh on 401 once and retry
api.interceptors.response.use(
  (response) => {
    loaderBus.dec();
    return response;
  },
  async (error: AxiosError) => {
    loaderBus.dec();

    const originalRequest: any = error.config || {};
    const status = error.response?.status;

    if (
      typeof window !== "undefined" &&
      status === 401 &&
      !originalRequest._retry &&
      getRefreshToken()
    ) {
      originalRequest._retry = true;

      try {
        const refreshToken = getRefreshToken()!;
        const res = await axios.post<{ access_token: string }>(
          `${API_URL}/auth/refresh`,
          { refresh_token: refreshToken }
        );

        const newAccessToken = res.data.access_token;
        localStorage.setItem("access_token", newAccessToken);

        // ensure headers are AxiosHeaders for the retried request too
        originalRequest.headers = AxiosHeaders.from(
          originalRequest.headers || {}
        );
        (originalRequest.headers as AxiosHeaders).set(
          "Authorization",
          `Bearer ${newAccessToken}`
        );

        // show loader around the retry call
        loaderBus.inc();
        return api(originalRequest);
      } catch (refreshErr) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        window.location.href = "/login";
        return Promise.reject(refreshErr);
      } finally {
        loaderBus.dec();
      }
    }

    return Promise.reject(error);
  }
);

export default api;
