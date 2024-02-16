//const API_URL = process.env.VUE_APP_API_URL || 'http://localhost:98/';
const API_URL = 'http://localhost:98/';

export const auth = {
    async getUserMe(token) {
        const response = await fetch(`${API_URL}users/me`, {
            method: 'GET',
            headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
            },
        });
        if (!response.ok) {
            throw new Error('' + response.status);
        }
        return response.json();
    },    
};