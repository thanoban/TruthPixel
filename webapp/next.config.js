/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // On this Windows local-dev setup, Next 14's output file tracing intermittently
  // fails after a successful compile/page generation step by looking for missing
  // generated trace artifacts under `.next/server/pages`. The public webapp does not
  // rely on standalone server bundling here, so disable tracing to keep local and CI
  // production builds deterministic.
  outputFileTracing: false,
};

module.exports = nextConfig;
