import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import './styles/base.css';
import { initTheme } from './composables/useTheme';
import { initUiPrefs } from './composables/useUiPrefs';

initTheme();
initUiPrefs();

const app = createApp(App);
app.use(router);
app.mount('#app');
