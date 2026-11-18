#include "atidaq/ATIDAQ/ftconfig.h"
const char *ati_serial(Calibration *c) { return c->Serial; }
int ati_channels(Calibration *c) { return c->rt.NumChannels; }
int ati_axes(Calibration *c) { return c->rt.NumAxes; }
int ati_tempcomp(Calibration *c) { return c->cfg.TempCompEnabled; }
