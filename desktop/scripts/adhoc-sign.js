// electron-builder afterPack hook: ad-hoc sign the macOS app bundle.
// Without a paid Apple certificate the app would be left with a broken signature,
// which Apple Silicon Macs report as "damaged". Ad-hoc signing (free) fixes that;
// users still confirm the first launch via right-click -> Open.
const { execFileSync } = require("node:child_process");
const path = require("node:path");

exports.default = async function adhocSign(context) {
  if (context.electronPlatformName !== "darwin") return;
  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  execFileSync("codesign", ["--force", "--deep", "--sign", "-", appPath], { stdio: "inherit" });
  execFileSync("codesign", ["--verify", "--deep", "--strict", appPath], { stdio: "inherit" });
  console.log(`  • ad-hoc signed ${appPath}`);
};
