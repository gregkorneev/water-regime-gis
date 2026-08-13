def classFactory(iface):
    from .plugin import WaterRegimeGisPlugin

    return WaterRegimeGisPlugin(iface)
