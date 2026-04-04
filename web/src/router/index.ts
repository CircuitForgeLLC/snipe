import { createRouter, createWebHistory } from 'vue-router'
import SearchView from '../views/SearchView.vue'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/',            component: SearchView },
    { path: '/listing/:id', component: () => import('../views/ListingView.vue') },
    { path: '/saved',       component: () => import('../views/SavedSearchesView.vue') },
    { path: '/blocklist',   component: () => import('../views/BlocklistView.vue') },
    // Catch-all — FastAPI serves index.html for all unknown routes (SPA mode)
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
