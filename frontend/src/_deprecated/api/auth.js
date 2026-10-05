import apiClient from './index.js';

export const register = (userData) => {
  return apiClient.post('register/', userData);
};

export const login = (credentials) => {
  return apiClient.post('login/', credentials);
}; 