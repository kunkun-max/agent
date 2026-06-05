import { createRouter, createWebHistory } from 'vue-router';
import { isLoggedIn } from '../services/api';
import LearnView from '../views/LearnView.vue';
import ResourcesView from '../views/ResourcesView.vue';
import ProfileView from '../views/ProfileView.vue';
import PathView from '../views/PathView.vue';
import LoginView from '../views/LoginView.vue';

const routes = [
  { path: '/', redirect: '/learn' },
  { path: '/login', component: LoginView },
  { path: '/learn', component: LearnView, meta: { requiresAuth: true } },
  { path: '/resources', component: ResourcesView, meta: { requiresAuth: true } },
  { path: '/profile', component: ProfileView, meta: { requiresAuth: true } },
  { path: '/path', component: PathView, meta: { requiresAuth: true } },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const loggedIn = isLoggedIn();
  if (to.meta.requiresAuth && !loggedIn) {
    return '/login';
  }
  if (to.path === '/login' && loggedIn) {
    return '/learn';
  }
  return true;
});

export default router;
