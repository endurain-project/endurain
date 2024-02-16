//const API_URL = process.env.VUE_APP_API_URL || 'http://localhost:98/';
const API_URL = 'http://localhost:98/';

export const auth = {
    isTokenValid(token) {
        if (!token) {
            return false;
        }

        const payload = JSON.parse(atob(token.split('.')[1]));
        const exp = payload.exp;
        const currentTime = Math.floor(Date.now() / 1000);

        return exp > currentTime;
    },
    storeLoggedUser(token, userMe) {
        localStorage.setItem('accessToken', token.access_token);
        localStorage.setItem('tokenType', token.token_type);
        localStorage.setItem('userMe', JSON.stringify(userMe));
    },
    removeLoggedUser() {
        localStorage.clear();
        //this.$router.push('/login');
    },
    async getToken(formData) {
        const response = await fetch(`${API_URL}token`, {
            method: 'POST',
            headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: formData
        });
        if (!response.ok) {
            throw new Error('' + response.status);
        }
        return response.json();
    },
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