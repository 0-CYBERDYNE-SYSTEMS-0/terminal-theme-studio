import QtQuick
import Quickshell
import qs.Ui

BarWidget {
  id: root
  moduleName: "scrimwiggins.foot-theme-studio"

  // The plugin folder is this repo, so bin/foot-theme-studio ships next to
  // this file. The registry stamps __sourceDir on the injected manifest;
  // without it (e.g. the manifest has not been passed in yet) fall back to
  // a PATH lookup.
  function launcherPath() {
    var dir = (root.manifest && root.manifest.__sourceDir) || ""
    return dir !== "" ? dir + "/bin/foot-theme-studio" : "foot-theme-studio"
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\uf1fc"
    fontFamily: "JetBrainsMono Nerd Font"
    horizontalMargin: 7.5
    tooltipText: "Foot Theme Studio"
    onPressed: function(mouseButton) {
      Quickshell.execDetached([root.launcherPath()])
    }
  }
}
