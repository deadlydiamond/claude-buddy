// `npm run dev` only: ?demo=tree or ?demo=chats preloads a state for README/website screenshots.
export const demo = import.meta.env.DEV ? new URLSearchParams(location.search).get('demo') : null
