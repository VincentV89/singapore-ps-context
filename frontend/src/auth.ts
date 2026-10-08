import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts';
import type { AppConfig } from './types';

export function isLocalPreview(config: AppConfig) {
  return config.localPreview === true && ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
}

export function createAuth(config: AppConfig) {
  if (!config.cognito?.authority || !config.cognito?.clientId) return null;
  return new UserManager({ authority: config.cognito.authority, client_id: config.cognito.clientId, redirect_uri: `${window.location.origin}/auth/callback`, post_logout_redirect_uri: `${window.location.origin}/`, response_type: 'code', scope: config.cognito.scope || 'openid profile life-events/access', automaticSilentRenew: true, userStore: new WebStorageStateStore({ store: window.sessionStorage }), monitorSession: false, revokeTokensOnSignout: false });
}

export async function getAuthenticatedUser(manager: UserManager | null): Promise<User | null> {
  if (!manager) return null;
  if (window.location.pathname === '/auth/callback') {
    const user = await manager.signinRedirectCallback();
    window.history.replaceState({}, '', '/');
    return user;
  }
  const user = await manager.getUser();
  return user && !user.expired ? user : null;
}

export async function signOut(manager: UserManager | null, config: AppConfig) {
  await manager?.removeUser();
  await manager?.clearStaleState();
  const domain = config.cognito.domain?.replace(/\/$/, '');
  if (domain && config.cognito.clientId) {
    const base = domain.startsWith('https://') ? domain : `https://${domain}`;
    window.location.assign(`${base}/logout?client_id=${encodeURIComponent(config.cognito.clientId)}&logout_uri=${encodeURIComponent(`${window.location.origin}/`)}`);
  } else window.location.replace('/');
}
