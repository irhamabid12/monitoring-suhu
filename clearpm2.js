const { exec } = require("child_process");
const schedule = require("node-schedule");

// Menjadwalkan PM2 flush setiap satu minggu sekali
schedule.scheduleJob("0 0 * * 0", function () {
    exec("pm2 flush", (error, stdout, stderr) => {
      if (error) {
        console.error(`Error saat menjalankan pm2 flush: ${error}`);
        return;
      }
      console.log("PM2 log berhasil di-flush setiap satu minggu sekali.");
    });
  });